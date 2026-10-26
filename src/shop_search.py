"""Search in the Shop: the grid's ranking, over the products the query names
(ADR 0031, amendment of 2026-10-17).

1. **Which products the words name**: `_search products` ordered by
   `$similarity` over the name, as Smart Search's baseline. `$score` is
   the text lift `exp(θ·bm25)`; exactly 1.0 means no query word matched,
   and those products are left out.
2. **How likely this shopper buys each**: the grid's `_recommend` `where`
   (`src/shop_ranking.py`) restricted to them, so the cart, the month and
   the household rule apply. Only `$p` is selected: a query word like
   "food" names hundreds of products.
3. **Ranked by P x text lift**, Smart Search's blend (`TEXT_THETA`). The
   top ones are asked once more through the grid's ranking, for their
   reasons, facts and the just-bought re-ask, and the page shows RESULTS
   of them, one card per name (`src/same_name.py`).

Why not Smart Search's one-query blend (`_search impressions get
product_sku`)? Its `where` only conditions `$p`: a filter on
`product_sku.*` doesn't narrow what it returns (probe, 2026-10-17), so a
grain-free household would be shown grain food.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from src.aito_client import AitoClient, AitoError
from src.same_name import one_per_name
from src.search_service import TEXT_THETA
from src.shop_ranking import ShopItem, ranked_items, shop_scope

RESULTS = 12
# Asked for reasons before one card per name, so RESULTS cards remain.
RANKED = 2 * RESULTS
# Every product is scored by `$similarity` (1.0 when no word matches), so
# the name query asks for the whole catalogue; a bigger one raises.
CATALOGUE_LIMIT = 1000


@dataclass(frozen=True)
class ShopSearch:
    query: str
    # False when no product name holds any query word: then there are no
    # results, and the page says why rather than show unrelated products.
    text_matched: bool
    items: list[ShopItem]
    last_query: dict

    def to_dict(self) -> dict:
        return asdict(self)


def search_shop(client: AitoClient, shopper_key: str, month: str, cart_skus: list[str], query: str,
                *, identity: bool = False, season: bool = True) -> ShopSearch:
    if not query.strip():
        raise ValueError("Search needs at least one word")
    scope = shop_scope(client, shopper_key, month, cart_skus, identity=identity, season=season)
    text_lift = _name_matches(client, query)
    candidates = [sku for sku in text_lift if sku not in cart_skus]
    if not candidates:
        return ShopSearch(query=query, text_matched=bool(text_lift), items=[],
                          last_query={"endpoint": "_search", "body": _name_query(query)})

    where = scope.where(only=candidates)
    hits = client.recommend("impressions", where, "product_sku", {"purchased": True},
                            select=["sku", "$p"], limit=len(candidates))["hits"]
    top = sorted(hits, key=lambda h: -h["$p"] * text_lift[h["sku"]])[:RANKED]

    items = ranked_items(client, scope, scope.where(only=[h["sku"] for h in top]), RANKED)
    items.sort(key=lambda i: -i.p * text_lift[i.sku])
    return ShopSearch(
        query=query, text_matched=True, items=one_per_name(items)[:RESULTS],
        last_query={"endpoint": "_recommend", "body": {
            "from": "impressions", "where": where, "recommend": "product_sku",
            "goal": {"purchased": True}, "select": ["sku", "$p"], "limit": len(candidates)}},
    )


def _name_matches(client: AitoClient, query: str) -> dict[str, float]:
    """{sku: text lift} for the products whose name holds a query word."""
    body = _name_query(query)
    res = client.search(body["from"], order_by=body["orderBy"], select=body["select"], limit=body["limit"])
    if res["total"] > len(res["hits"]):
        raise AitoError(f"The catalogue has {res['total']} products, more than the {CATALOGUE_LIMIT} "
                        "the Shop's search reads")
    return {h["sku"]: float(h["$score"]) for h in res["hits"] if h["$score"] > 1.0}


def _name_query(query: str) -> dict:
    return {"from": "products", "orderBy": {"$similarity": {"name": query}, "theta": TEXT_THETA},
            "select": ["sku", "$score"], "limit": CATALOGUE_LIMIT}
