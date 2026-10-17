"""The Shop's product drawer: the product, its alternatives, and what goes
with it (ADR 0031).

- **Details**: the catalogue row, and this month's offer (`shop_offers`).
- **Alternatives**: the grid's ranking (`src/shop_ranking.py`) over the
  same category for the same pet, the product itself and the cart left
  out: what this shopper would most likely buy instead, with reasons. A
  kit item's category ("accessories") holds cages and bottles alike, so
  for one the name must also hold its type: another water bottle.
- **Often in the same basket**: `_relate` on `orders`, where the order's
  SKUs hold this one, related to `skus`. Pairs are thin per product (a few
  orders each), so every row shows its count, and a pair is kept only with
  at least MIN_TOGETHER orders and a 95 % interval above 1.
- **In your orders**: the shopper's own orders that held it, by `_search`.
  This is their history, not a prediction: `_relate` over one shopper's
  orders (a nested `from`) isn't supported on Aito 2.11.4 (501).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from src.aito_client import AitoClient
from src.aito_compat import related_value
from src.lookup_errors import UnknownProductError
from src.price_bands import lift_interval
from src.shop_context import DURABLE_TYPES, item_type
from src.shop_offers import offers_this_month
from src.shop_ranking import ShopItem, ranked_items, shop_scope

PAIRS = 6
ALTERNATIVES = 4
# A pair seen in fewer orders than this isn't shown as "often" together,
# whatever its interval says: three orders is an anecdote.
MIN_TOGETHER = 5


@dataclass(frozen=True)
class BasketPair:
    sku: str
    name: str
    lift: float
    together: int       # orders holding both
    orders_with_it: int  # orders holding this drawer's product


@dataclass(frozen=True)
class ProductDrawer:
    product: dict
    offer_pct: float | None  # this month's offer, a fact from price_history
    alternatives: list[ShopItem]
    same_basket: list[BasketPair]
    your_orders: list[str]   # months of the shopper's orders that held it
    last_query: dict

    def to_dict(self) -> dict:
        return asdict(self)


def get_product_drawer(client: AitoClient, sku: str, shopper_key: str, month: str,
                       cart_skus: list[str]) -> ProductDrawer:
    found = client.search("products", where={"sku": sku}, limit=1)["hits"]
    if not found:
        raise UnknownProductError(f"No product {sku} in the catalogue")
    product = found[0]
    scope = shop_scope(client, shopper_key, month, cart_skus)
    same_kind = {**scope.where(exclude=[sku]),
                 "product_sku.category": product["category"], "product_sku.pet_type": product["pet_type"]}
    if (kind := item_type(product["name"], product["brand"])) in DURABLE_TYPES:
        same_kind["product_sku.name"] = {"$match": kind}
    alternatives = ranked_items(client, scope, same_kind, ALTERNATIVES)

    body = {"from": "orders", "where": {"skus": {"$match": sku}}, "relate": "skus", "limit": 40}
    hits = client.relate(table="orders", where=body["where"], relate_field="skus", limit=40)["hits"]

    pairs = []
    for hit in hits:
        other = related_value(hit, "skus")
        fs = hit["fs"]
        low, _ = lift_interval(float(hit["lift"]), fs["fOnCondition"], fs["fCondition"], fs["f"], fs["n"])
        if other != sku and fs["fOnCondition"] >= MIN_TOGETHER and low > 1:
            pairs.append((other, hit))
    pairs = pairs[:PAIRS]
    names = _names(client, [other for other, _ in pairs])
    same_basket = [BasketPair(other, names[other], round(float(h["lift"]), 2),
                              int(h["fs"]["fOnCondition"]), int(h["fs"]["fCondition"]))
                   for other, h in pairs]

    # Their own orders before the picked month that held it: history, as of then.
    mine = [o["month"] for o in scope.orders if sku in o["skus"].split()]
    return ProductDrawer(
        product=product, offer_pct=offers_this_month(client, [sku], month).get(sku),
        alternatives=alternatives, same_basket=same_basket,
        your_orders=mine,
        last_query={"endpoint": "_relate", "body": body},
    )


def _names(client: AitoClient, skus: list[str]) -> dict[str, str]:
    if not skus:
        return {}
    rows = client.search("products", where={"sku": {"$or": skus}}, limit=len(skus))["hits"]
    return {p["sku"]: p["name"] for p in rows}
