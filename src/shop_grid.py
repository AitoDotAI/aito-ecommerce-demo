"""The Shop's grid: what to show this shopper now (ADR 0031).

The shopper's top products by `src/shop_ranking.py`: `_recommend` with
their profile, the month and the cart as context, the household rule as a
filter, and the last order's items re-asked as just bought. One card per
product name (`src/same_name.py`).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace

from src.aito_client import AitoClient
from src.same_name import one_per_name
from src.shop_context import pets_filter
from src.shop_ranking import PRODUCT_FIELDS, ShopItem, ranked_items, shop_scope
from src.shop_rescore import RESCORED, rescore

GRID_SIZE = 12
CANDIDATES = 24     # ranked before the just-bought re-ask and one card per name, so the grid stays full


@dataclass(frozen=True)
class ShopGrid:
    shopper: dict
    month: str
    rule: str | None
    cart: list[dict]
    items: list[ShopItem]
    last_order_skus: list[str]
    last_query: dict
    rescored: bool = False   # re-scored by the sandbox's 2026-05 states (ADR 0043)
    identity: bool = False   # also conditioned on the customer themselves (the experiment)
    trust: bool = False      # ...and not narrowed to the household's pets
    recent: bool = False     # the last order's items are in the context as if in the cart

    def to_dict(self) -> dict:
        return asdict(self)


def get_shop_grid(client: AitoClient, shopper_key: str, month: str, cart_skus: list[str],
                  *, rescored: bool = False, identity: bool = False, trust: bool = False,
                  recent: bool = False) -> ShopGrid:
    """`rescored`: the sandbox's Shop for 2026-05, its top RESCORED candidates
    re-scored by the states the owner's levers wrote (`src/shop_rescore.py`)."""
    scope = shop_scope(client, shopper_key, month, cart_skus, identity=identity, recent_basket=recent)
    # "Picked for you" shows the household's own pets' products; search and a
    # product's alternatives don't (a cat owner may look for a dog gift).
    # `trust`: with the customer in the query, let their own history decide and don't also filter by pets.
    # A thin history then shows other pets' products (a guinea pig household sees dog treats).
    where = scope.where() if identity and trust else {**scope.where(), **pets_filter(scope.pets)}
    candidates = RESCORED if rescored else CANDIDATES
    items = ranked_items(client, scope, where, candidates)
    items = _rescored(client, items, month) if rescored else one_per_name(items)
    return ShopGrid(
        shopper=scope.shopper.to_dict(), month=month, rule=scope.rule, cart=scope.cart,
        items=items[:GRID_SIZE], last_order_skus=scope.last_order_skus,
        last_query={"endpoint": "_recommend", "body": {
            "from": "impressions", "where": where, "recommend": "product_sku",
            "goal": {"purchased": True}, "select": PRODUCT_FIELDS + ["$p", "$why"], "limit": candidates}},
        rescored=rescored, identity=identity, trust=identity and trust, recent=recent,
    )


def _rescored(client: AitoClient, items: list[ShopItem], month: str) -> list[ShopItem]:
    """Re-scored, one card per name; a product a lever changed wins its name.

    A card's measured rank is its name's place in the measured Shop, which
    also shows one card per name, so "↑ 9 since the offer" counts the cards
    the viewer saw move.
    """
    measured_place = {item.name: place for place, item in enumerate(one_per_name(items), start=1)}
    cards = one_per_name(rescore(client, items, month), wins=lambda item: item.adjustment is not None)
    return [replace(card, measured_rank=measured_place[card.name]) for card in cards]
