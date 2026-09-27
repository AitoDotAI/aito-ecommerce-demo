"""The search systems under evaluation ("arms"), each `(client, q, k) -> [sku]`.

Every arm searches the SAME text — the product `name` — so a difference
between arms is a difference in method, not in what it was allowed to read
(see relevance.py on why that matters for a vector arm).

Three kinds of arm:
  - BEFORE: Smart Search's two columns as they were before ADR 0026, kept
    frozen here so "both columns improved" stays reproducible.
  - NOW: the columns as the page runs them, called through search_service
    itself, so the harness measures the shipped code, not a copy.
  - CONTROLS: rankings that must NOT score well (see run.py).
The vector arms (`$nearest`, `hybrid`, the three-way blend) join with
ADR 0026 step 2.
"""

from __future__ import annotations

import random
from typing import Callable

from src.aito_client import AitoClient
from src.search_service import PERSONAS, _baseline_search, predictive_blend_body

Arm = Callable[[AitoClient, str, int], list[str]]


# ── BEFORE ───────────────────────────────────────────────────────────


def before_match(client: AitoClient, q: str, k: int) -> list[str]:
    """The old left column: every query token must occur in the name
    (`$match` is AND), results in table order, no ranking. Natural
    phrasing like "food for an old dog" returns nothing."""
    res = client.search("products", where={"name": {"$match": q}}, limit=k)
    return [h["sku"] for h in res["hits"]]


def before_predictive(persona_id: str) -> Arm:
    """The old right column: `_recommend` over impressions with a
    `product_sku.name $match` candidate filter. It could only reorder what
    `$match` let through, so its relevance equalled `before_match`."""
    persona = PERSONAS[persona_id]

    def arm(client: AitoClient, q: str, k: int) -> list[str]:
        where: dict[str, object] = {"product_sku.name": {"$match": q}, "search_query": q,
                                    "customer_segment": persona.segment}
        if persona.pet_size is not None:
            where["customer_pet_size"] = persona.pet_size
        res = client.recommend(table="impressions", where=where, recommend_field="product_sku",
                               goal={"purchased": True},
                               based_on=["pet_type", "brand", "dietary", "category"], limit=k)
        return [h["sku"] for h in res["hits"]]
    return arm


# ── NOW (the shipped code) ───────────────────────────────────────────


def left_bm25(client: AitoClient, q: str, k: int) -> list[str]:
    """The left column: BM25 over the name; rows matching no query word
    dropped (they would arrive in table order — see `table_order_control`)."""
    return [h.sku for h in _baseline_search(client, q, k)]


def right_blend(persona_id: str, text_theta: float) -> Arm:
    """The right column for one persona: P(purchase) x BM25 lift in one
    `$multiply` orderBy, built by the page's own `predictive_blend_body`.
    `text_theta` is swept by run.py to show why the shipped value was chosen."""
    persona = PERSONAS[persona_id]

    def arm(client: AitoClient, q: str, k: int) -> list[str]:
        body = predictive_blend_body(q, persona, k, text_theta=text_theta)
        res = client.search(table=body["from"], get=body["get"], where=body["where"],
                            order_by=body["orderBy"], select=["sku"], limit=k)
        return [h["sku"] for h in res["hits"]]
    return arm


# ── CONTROLS ─────────────────────────────────────────────────────────


def random_control(skus: list[str]) -> Arm:
    """CONTROL: a seeded random ranking of the catalogue. Its score is the
    CHANCE level every real arm is measured against (see run.py)."""
    def arm(_client: AitoClient, q: str, k: int) -> list[str]:
        ranked = list(skus)
        random.Random(q).shuffle(ranked)
        return ranked[:k]
    return arm


def table_order_control(skus: list[str]) -> Arm:
    """CONTROL: the first k products of the table, whatever the query. The
    table starts with dog dry food, so this gets free credit on every dog
    query. An arm that falls back to table order when nothing matches
    (unfiltered BM25 did) inherits that credit; this shows how much."""
    def arm(_client: AitoClient, _q: str, k: int) -> list[str]:
        return skus[:k]
    return arm
