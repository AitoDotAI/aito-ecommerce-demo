"""Which products are on offer this month: a fact from `product_states`.

Shown as a fact beside Aito's reasons (ADR 0031, amendment of
2026-10-17). Once the Shop recommends product states (ADR 0032), an offer
can be one of the reasons instead.
"""

from __future__ import annotations

from src.aito_client import AitoClient, AitoError

def states_this_month(client: AitoClient, skus: list[str], month: str) -> dict[str, dict]:
    """{sku: its `product_states` row} for `month`."""
    if not skus:
        return {}
    res = client.search("product_states", where={"month": month, "product_sku": {"$or": skus}},
                        limit=len(skus))
    if res["total"] > len(res["hits"]):
        raise AitoError(f"product_states has {res['total']} rows for {len(skus)} products in {month}: "
                        "more than one per product and month")
    return {row["product_sku"]: row for row in res["hits"]}


def offers_of(states: dict[str, dict]) -> dict[str, float]:
    """{sku: percent off list} for the products on offer."""
    # `on_offer` is set by the data: at least 10 % off, beyond the ±2 % noise.
    return {sku: float(row["discount_pct"]) for sku, row in states.items() if row["on_offer"]}


def offers_this_month(client: AitoClient, skus: list[str], month: str) -> dict[str, float]:
    """{sku: percent off list} for the products on offer in `month`."""
    return offers_of(states_this_month(client, skus, month))
