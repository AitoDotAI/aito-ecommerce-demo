"""The Shop's grid: what to show this shopper now (ADR 0031).

1. `_recommend` on `impressions`, goal `purchased`, with the shopper's
   profile, the month and the cart as context (`shop_context`), the
   household rule as a filter on the candidates, and the cart's own items
   left out.
2. Anything the shopper bought in their last order is re-asked, in one
   `_batch`, as `_predict purchased` with `just_bought: true`: Aito has
   learned that a shopper rarely re-buys what they just bought (ADR 0030,
   check A8), so those fall down the grid, and the card shows by how much.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from src.aito_client import AitoClient, AitoError
from src.lookup_errors import UnknownProductError
from src.shop_context import rule_filter, shopper_where
from src.shop_personas import shopper

GRID_SIZE = 12
CANDIDATES = 20     # ranked before the just-bought re-ask, so the grid stays full


@dataclass(frozen=True)
class ShopItem:
    sku: str
    name: str
    brand: str
    pet_type: str
    category: str
    price_eur: float
    p: float                        # P(purchased) for this shopper, now
    p_if_new: float | None = None   # for a just-bought item: its P before the re-ask


@dataclass(frozen=True)
class ShopGrid:
    shopper: dict
    month: str
    rule: str | None
    cart: list[dict]
    items: list[ShopItem]
    last_order_skus: list[str]
    last_query: dict

    def to_dict(self) -> dict:
        return asdict(self)


def get_shop_grid(client: AitoClient, shopper_key: str, month: str, cart_skus: list[str]) -> ShopGrid:
    s = shopper(shopper_key)
    customer = client.search("customers", where={"customer_id": s.customer_id}, limit=1)["hits"][0]
    cart = _cart(client, cart_skus)
    rule = customer.get("diet_rule")

    context = shopper_where(customer, cart, month)
    where = dict(context)
    if (keeps_rule := rule_filter(rule)) is not None:
        where.update(keeps_rule)
    if cart_skus:
        where["product_sku"] = {"$not": {"$or": cart_skus}}
    hits = client.recommend("impressions", where, "product_sku", {"purchased": True}, limit=CANDIDATES)["hits"]
    items = [_item(h) for h in hits]

    last = _last_order_skus(client, s.customer_id, month)
    items = _reask_just_bought(client, context, items, set(last))
    items.sort(key=lambda i: -i.p)
    return ShopGrid(
        shopper=s.to_dict(), month=month, rule=rule, cart=cart, items=items[:GRID_SIZE],
        last_order_skus=last,
        last_query={"endpoint": "_recommend", "body": {
            "from": "impressions", "where": where, "recommend": "product_sku",
            "goal": {"purchased": True}, "limit": CANDIDATES}},
    )


def _cart(client: AitoClient, skus: list[str]) -> list[dict]:
    if not skus:
        return []
    found = {p["sku"]: p for p in client.search("products", where={"sku": {"$or": skus}}, limit=len(skus))["hits"]}
    missing = [s for s in skus if s not in found]
    if missing:
        raise UnknownProductError(f"No product {', '.join(missing)} in the catalogue")
    return [found[s] for s in skus]


def _last_order_skus(client: AitoClient, customer_id: str, month: str) -> list[str]:
    """The shopper's last order before `month`, as the generator defines it."""
    orders = client.search("orders", where={"customer_id": customer_id}, limit=200)["hits"]
    earlier = sorted((o for o in orders if o["month"] < month), key=lambda o: o["month"])
    return earlier[-1]["skus"].split() if earlier else []


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
    return [ShopItem(**{**asdict(i), "p": p_now[i.sku], "p_if_new": i.p}) if i.sku in p_now else i
            for i in items]


def _p_true(answer: dict, sku: str) -> float:
    for hit in answer.get("hits", []):
        if hit.get("feature", hit.get("$value")) is True:
            return float(hit["$p"])
    raise AitoError(f"_predict purchased for {sku} had no `true` hit: {str(answer)[:200]}")


def _item(hit: dict) -> ShopItem:
    return ShopItem(sku=hit["sku"], name=hit["name"], brand=hit["brand"], pet_type=hit["pet_type"],
                    category=hit["category"], price_eur=float(hit["price_eur"]), p=float(hit["$p"]))
