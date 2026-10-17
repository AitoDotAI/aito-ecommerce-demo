"""The Shop's grid: what to show this shopper now (ADR 0031).

The shopper's top products by `src/shop_ranking.py`: `_recommend` with
their profile, the month and the cart as context, the household rule as a
filter, and the last order's items re-asked as just bought.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from src.aito_client import AitoClient
from src.shop_ranking import PRODUCT_FIELDS, ShopItem, ranked_items, shop_scope

GRID_SIZE = 12
CANDIDATES = 20     # ranked before the just-bought re-ask, so the grid stays full


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
    scope = shop_scope(client, shopper_key, month, cart_skus)
    where = scope.where()
    items = ranked_items(client, scope, where, CANDIDATES)
    return ShopGrid(
        shopper=scope.shopper.to_dict(), month=month, rule=scope.rule, cart=scope.cart,
        items=items[:GRID_SIZE], last_order_skus=scope.last_order_skus,
        last_query={"endpoint": "_recommend", "body": {
            "from": "impressions", "where": where, "recommend": "product_sku",
            "goal": {"purchased": True}, "select": PRODUCT_FIELDS + ["$p", "$why"], "limit": CANDIDATES}},
    )
