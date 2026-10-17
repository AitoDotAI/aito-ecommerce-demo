"""Which products are on offer this month: a fact from `price_history`.

Shown as a fact, not as a reason Aito found: `impressions` records no
offer, so no query can say how much an offer lifts a purchase (ADR 0031,
amendment of 2026-10-17).
"""

from __future__ import annotations

from src.aito_client import AitoClient, AitoError

# `discount_pct` carries ±2 % of noise around the list price (ADR 0016);
# below this it isn't an offer a shopper would notice.
OFFER_MIN_PCT = 10.0


def offers_this_month(client: AitoClient, skus: list[str], month: str) -> dict[str, float]:
    """{sku: percent off list} for the products on offer in `month`."""
    if not skus:
        return {}
    res = client.search("price_history", where={"month": month, "product_sku": {"$or": skus}},
                        limit=len(skus))
    if res["total"] > len(res["hits"]):
        raise AitoError(f"price_history has {res['total']} rows for {len(skus)} products in {month}: "
                        "more than one per product and month")
    return {row["product_sku"]: float(row["discount_pct"]) for row in res["hits"]
            if row["discount_pct"] >= OFFER_MIN_PCT}
