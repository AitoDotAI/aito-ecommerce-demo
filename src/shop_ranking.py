"""How the Shop ranks products for a shopper (ADR 0031): shared by the
grid, search and a product's alternatives.

1. `_recommend` on `impressions`, goal `purchased`, with the shopper's
   profile, the month and the cart as context (`shop_context`), the
   household rule as a filter on the candidates, and the cart's own items
   left out. Its `$why` gives each product's reasons (`shop_reasons`).
2. Anything the shopper bought in their last order is re-asked, in one
   `_batch`, as `_predict purchased` with `just_bought: true`: Aito has
   learned that a shopper rarely re-buys what they just bought (ADR 0030,
   check A8), so those fall, and the card shows by how much.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from src.aito_client import AitoClient, AitoError
from src.lookup_errors import UnknownProductError
from src.shop_context import FOOD, basket_words, rule_filter, shopper_where, shopper_where_from_orders
from src.shop_history import orders_before
from src.shop_features import ProductFeature, product_features
from src.shop_offers import offers_of, states_this_month
from src.shop_personas import Shopper, shopper
from src.shop_reasons import CART, LAST_ORDER, PETS, Reason, reasons_for
from src.shop_rescore import ScoreAdjustment
from src.shop_why import shop_why

PRODUCT_FIELDS = ["sku", "name", "brand", "pet_type", "category", "price_eur", "avg_rating", "tags"]


@dataclass(frozen=True)
class ShopItem:
    sku: str
    name: str
    brand: str
    pet_type: str
    category: str
    price_eur: float
    p: float                        # P(purchased) for this shopper, now
    reasons: list[Reason]           # Aito's: what lifts this product for this shopper
    avg_rating: float | None        # facts, not reasons: the data can't say
    offer_pct: float | None         # how much they lift a purchase
    keeps_rule: bool                # food that keeps the household's rule
    p_if_new: float | None = None   # for a just-bought item: its P before the re-ask
    # The sandbox's re-scored Shop (ADR 0043, src/shop_rescore.py):
    measured_rank: int | None = None          # its rank by Aito's $p, before re-scoring
    adjustment: ScoreAdjustment | None = None  # set when its 2026-05 state re-scored it
    # Other SKUs of the same name this card stands for (`src/same_name.py`).
    same_name_skus: list[str] = field(default_factory=list)
    # The full `$why` chain behind `p`, for the card's ? popover (src/shop_why.py); `reasons`
    # above is its short form. None once `p` is re-asked (just bought): the chain is the old one.
    why_explanation: dict | None = None
    # The tokens behind "this one's features" (src/shop_features.py): the one term of the chain
    # `$why` can't break down.
    features: list[ProductFeature] = field(default_factory=list)


@dataclass(frozen=True)
class ShopScope:
    """Who is shopping, when, and with what in the cart."""
    shopper: Shopper
    month: str
    rule: str | None
    pets: str               # declared by the household: "dog cat"; else read from its orders
    pets_declared: bool
    cart: list[dict]
    context: dict           # the `where` as context: declared pets, month, cart
    orders: list[dict]      # the shopper's orders before `month`, oldest first
    recent_basket: bool = False   # the last order's items are in the context as if in the cart (an experiment)

    @property
    def last_order_skus(self) -> list[str]:
        return self.orders[-1]["skus"].split() if self.orders else []

    def where(self, *, only: list[str] | None = None, exclude: list[str] = ()) -> dict:
        """The `_recommend` where: context, the rule filter, and which candidates."""
        # Ranked as if not just bought; items from the last order are re-asked.
        where = {**self.context, "just_bought": False}
        if (keeps_rule := rule_filter(self.rule)) is not None:
            where.update(keeps_rule)
        left_out = [p["sku"] for p in self.cart] + list(exclude)
        if only is not None:
            where["product_sku"] = {"$or": [s for s in only if s not in left_out]}
        elif left_out:
            where["product_sku"] = {"$not": {"$or": left_out}}
        return where


IDENTITY = "context.customer"    # the customer themselves: their own showings and what they did


def shop_scope(client: AitoClient, shopper_key: str, month: str, cart_skus: list[str],
               *, identity: bool = False, recent_basket: bool = False) -> ShopScope:
    """`identity`: also condition on the customer themselves (`context.customer`), beside their pets.
    Off by default: the sweeps found it ties on ranking and overconfides the probabilities (ADR 0033);
    it is an experiment."""
    s = shopper(shopper_key)
    customer = client.search("customers", where={"customer_id": s.customer_id}, limit=1)["hits"][0]
    cart = _cart(client, cart_skus)
    orders = orders_before(client, s.customer_id, month)
    declared = customer.get("pets")
    if declared:
        pets, context = declared, shopper_where(declared, cart, month)
    else:
        # Most customers declare no pet profile (ADR 0045). Their pets are those of
        # their orders. Provisional: P, the form that needs no identity and so also
        # serves a shopper who declined tracking; the no-profile sweep
        # (actionable-states-prereg.md) hasn't concluded which form the Shop keeps.
        pets = _pets_of_orders(client, orders)
        if not pets:
            raise UnknownShopperProfileError(
                f"{s.customer_id} declared no pets and has no order before {month}: the Shop has nothing to read")
        context = shopper_where_from_orders(pets, cart, month)
    if recent_basket and orders:
        # Start from the last order: its items give the pets, and where the shopper is (the first items for a
        # terrarium, or a new puppy's second week), as the cart's words do for the session in hand.
        last = _cart(client, sorted(set(orders[-1]["skus"].split())))
        words = basket_words(last + cart)
        context = {**context, "context.basket_categories": {"$and": [{"$match": w} for w in words]}}
    if identity:
        # An id condition uses only the rows that carry that id: it brings none of the customer's fields,
        # and an id with no rows is no evidence at all (core, 2026-10-25). The pets stay, as a path.
        context = {**context, IDENTITY: s.customer_id}
    return ShopScope(shopper=s, month=month, rule=customer.get("diet"), pets=pets, pets_declared=bool(declared),
                     cart=cart, context=context, orders=orders, recent_basket=recent_basket)


class UnknownShopperProfileError(LookupError):
    """A shopper with no declared pets and no earlier order."""


def _pets_of_orders(client: AitoClient, orders: list[dict]) -> str:
    """The pet types of the products in `orders`, as `contexts.pets_from_orders` writes them."""
    skus = sorted({sku for o in orders for sku in o["skus"].split()})
    if not skus:
        return ""
    found = client.search("products", where={"sku": {"$or": skus}}, limit=len(skus))["hits"]
    if len(found) != len(skus):
        raise AitoError(f"Orders hold {len(skus)} products, the catalogue returned {len(found)}")
    return " ".join(sorted({p["pet_type"] for p in found}))


def ranked_items(client: AitoClient, scope: ShopScope, where: dict, limit: int) -> list[ShopItem]:
    """The `_recommend` for `where`, with reasons, facts and the just-bought re-ask, by P."""
    hits = client.recommend("impressions", where, "product_sku", {"purchased": True},
                            select=PRODUCT_FIELDS + ["$p", "$why"], limit=limit)["hits"]
    states = states_this_month(client, [h["sku"] for h in hits], scope.month)
    offers = offers_of(states)
    items = [_item(h, scope.context, states.get(h["sku"]), offers.get(h["sku"]), scope.rule is not None, scope.pets.split(),
                   LAST_ORDER if scope.recent_basket and not scope.cart else CART)
             for h in hits]
    items = _reask_just_bought(client, scope.context, items, set(scope.last_order_skus))
    return sorted(items, key=lambda i: -i.p)


def _cart(client: AitoClient, skus: list[str]) -> list[dict]:
    if not skus:
        return []
    if len(set(skus)) != len(skus):
        raise ValueError(f"The cart lists a product twice: {', '.join(skus)}")
    found = {p["sku"]: p for p in client.search("products", where={"sku": {"$or": skus}}, limit=len(skus))["hits"]}
    missing = [s for s in skus if s not in found]
    if missing:
        raise UnknownProductError(f"No product {', '.join(missing)} in the catalogue")
    return [found[s] for s in skus]


def _reask_just_bought(client: AitoClient, context: dict, items: list[ShopItem], last: set[str]) -> list[ShopItem]:
    just = [i for i in items if i.sku in last]
    if not just:
        return items
    answers = client.batch([
        {"from": "impressions", "where": {**context, "product_sku": i.sku, "just_bought": True},
         "predict": "purchased"}
        for i in just
    ])
    p_now = {i.sku: _p_true(a, i.sku) for i, a in zip(just, answers)}
    return [replace(i, p=p_now[i.sku], p_if_new=i.p, why_explanation=None) if i.sku in p_now else i for i in items]


def _p_true(answer: dict, sku: str) -> float:
    for hit in answer.get("hits", []):
        if hit.get("feature", hit.get("$value")) is True:
            return float(hit["$p"])
    raise AitoError(f"_predict purchased for {sku} had no `true` hit: {str(answer)[:200]}")


def _item(hit: dict, context: dict, state: dict | None, offer_pct: float | None, has_rule: bool, pets: list[str],
          cart_label: str = CART) -> ShopItem:
    rating = hit.get("avg_rating")
    reasons = reasons_for(hit["$why"], hit["sku"], cart_label)
    if hit["pet_type"] not in pets:
        # Search shows other pets' products too (a gift). The declared pets can
        # still lift one, on a handful of impressions, but "fits your pets" it doesn't.
        reasons = [r for r in reasons if r.label != PETS]
    return ShopItem(
        sku=hit["sku"], name=hit["name"], brand=hit["brand"], pet_type=hit["pet_type"],
        category=hit["category"], price_eur=float(hit["price_eur"]), p=float(hit["$p"]),
        reasons=reasons,
        why_explanation=shop_why(hit["$why"], float(hit["$p"]), context),
        features=product_features(hit, state),
        avg_rating=None if rating is None else float(rating),
        offer_pct=offer_pct,
        # The rule filter lets through only food that keeps the rule.
        keeps_rule=has_rule and hit["category"] in FOOD and hit["pet_type"] in ("dog", "cat"),
    )
