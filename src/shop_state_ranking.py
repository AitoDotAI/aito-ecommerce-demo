"""The Shop's ranking with the product's state as the candidate (ADR 0065).

    {"from": "impressions",
     "where": {<the shopper's context>, "product_state.month": "2026-04",
               "product_state.product_sku.pet_type": {"$or": ["dog"]}, ...},
     "recommend": "product_state", "goal": {"purchased": true},
     "select": ["product_state_id", "product_sku", "$p", "$why"]}

The candidates are the month's `product_states` rows, so the price, offer band and stars the shopper would see are
what Aito is asked about; the product ranking sees them only as history. A hit is the state's id and its product's
sku (bare); the card's product fields come from `products`. The filters that speak of the product
(`product_sku.pet_type`, the household rule, the cart) reach it one link further, through `product_state`.
"""

from __future__ import annotations

from src.aito_client import AitoClient, AitoError
from src.shop_ranking import ShopItem, ShopScope, items_from_hits

STATE_SELECT = ["product_state_id", "product_sku", "$p", "$why"]


def through_state(where: object) -> object:
    """`where` with every field of the product reached through the state: `product_sku.x` → `product_state.product_sku.x`."""
    if isinstance(where, dict):
        return {(f"product_state.{key}" if key == "product_sku" or key.startswith("product_sku.") else key): through_state(value)
                for key, value in where.items()}
    if isinstance(where, list):
        return [through_state(value) for value in where]
    return where


def state_body(where: dict, month: str, limit: int) -> dict:
    """The `_recommend` that ranks the month's states for the product ranking's `where`."""
    return {"from": "impressions", "where": {**through_state(where), "product_state.month": month},
            "recommend": "product_state", "goal": {"purchased": True}, "select": STATE_SELECT, "limit": limit}


def state_ranked_items(client: AitoClient, scope: ShopScope, where: dict, limit: int) -> list[ShopItem]:
    """The month's states ranked by P(purchased), as cards of their products."""
    body = state_body(where, scope.month, limit)
    hits = client.recommend(body["from"], body["where"], "product_state", body["goal"], select=STATE_SELECT, limit=limit)["hits"]
    skus = [h["product_sku"] for h in hits]
    products = {p["sku"]: p for p in client.search("products", where={"sku": {"$or": skus}}, limit=len(skus))["hits"]} if skus else {}
    if missing := [s for s in skus if s not in products]:
        raise AitoError(f"The state ranking for {scope.month} names products not in the catalogue: {', '.join(missing)}")
    cards = [{**products[h["product_sku"]], "$p": h["$p"], "$why": h["$why"]} for h in hits]
    return items_from_hits(client, scope, cards, link="product_state",
                           state_ids={h["product_sku"]: h["product_state_id"] for h in hits})
