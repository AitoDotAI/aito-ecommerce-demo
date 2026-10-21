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

from dataclasses import dataclass, replace

from src.aito_client import AitoClient, AitoError
from src.lookup_errors import UnknownProductError
from src.shop_context import FOOD, rule_filter, shopper_where
from src.shop_history import orders_before
from src.shop_offers import offers_this_month
from src.shop_personas import Shopper, shopper
from src.shop_reasons import Reason, reasons_for

PRODUCT_FIELDS = ["sku", "name", "brand", "pet_type", "category", "price_eur", "avg_rating"]


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


@dataclass(frozen=True)
class ShopScope:
    """Who is shopping, when, and with what in the cart."""
    shopper: Shopper
    month: str
    rule: str | None
    pets: str               # declared by the household: "dog cat"
    cart: list[dict]
    context: dict           # the `where` as context: declared pets, month, cart
    orders: list[dict]      # the shopper's orders before `month`, oldest first

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


def shop_scope(client: AitoClient, shopper_key: str, month: str, cart_skus: list[str]) -> ShopScope:
    s = shopper(shopper_key)
    customer = client.search("customers", where={"customer_id": s.customer_id}, limit=1)["hits"][0]
    cart = _cart(client, cart_skus)
    orders = orders_before(client, s.customer_id, month)
    context = shopper_where(customer["pets"], cart, month)
    return ShopScope(shopper=s, month=month, rule=customer.get("diet"), pets=customer["pets"], cart=cart,
                     context=context, orders=orders)


def ranked_items(client: AitoClient, scope: ShopScope, where: dict, limit: int) -> list[ShopItem]:
    """The `_recommend` for `where`, with reasons, facts and the just-bought re-ask, by P."""
    hits = client.recommend("impressions", where, "product_sku", {"purchased": True},
                            select=PRODUCT_FIELDS + ["$p", "$why"], limit=limit)["hits"]
    offers = offers_this_month(client, [h["sku"] for h in hits], scope.month)
    items = [_item(h, offers.get(h["sku"]), scope.rule is not None) for h in hits]
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
    return [replace(i, p=p_now[i.sku], p_if_new=i.p) if i.sku in p_now else i for i in items]


def _p_true(answer: dict, sku: str) -> float:
    for hit in answer.get("hits", []):
        if hit.get("feature", hit.get("$value")) is True:
            return float(hit["$p"])
    raise AitoError(f"_predict purchased for {sku} had no `true` hit: {str(answer)[:200]}")


def _item(hit: dict, offer_pct: float | None, has_rule: bool) -> ShopItem:
    rating = hit.get("avg_rating")
    return ShopItem(
        sku=hit["sku"], name=hit["name"], brand=hit["brand"], pet_type=hit["pet_type"],
        category=hit["category"], price_eur=float(hit["price_eur"]), p=float(hit["$p"]),
        reasons=reasons_for(hit["$why"], hit["sku"]),
        avg_rating=None if rating is None else float(rating),
        offer_pct=offer_pct,
        # The rule filter lets through only food that keeps the rule.
        keeps_rule=has_rule and hit["category"] in FOOD and hit["pet_type"] in ("dog", "cat"),
    )
