"""The search systems under evaluation ("arms"), each `(client, q, k) -> [sku]`.

Every arm searches the SAME text — the product `name` — so a difference
between arms is a difference in method, not in what it was allowed to read
(see relevance.py on why that matters for a vector arm).

Arms are added here as they become available. The vector arms (`$nearest`,
`hybrid`, the three-way `$multiply`) join once the Vector column and the
seeded product embeddings land.
"""

from __future__ import annotations

import random
from typing import Callable

from src.aito_client import AitoClient

Arm = Callable[[AitoClient, str, int], list[str]]


def current_match(client: AitoClient, q: str, k: int) -> list[str]:
    """Smart Search's baseline column today: every query token must occur
    in the name (`$match` is AND), results in index order, no ranking.
    Natural phrasing like "food for an old dog" returns nothing."""
    res = client.search("products", where={"name": {"$match": q}}, limit=k)
    return [h["sku"] for h in res.get("hits", [])]


def bm25(client: AitoClient, q: str, k: int) -> list[str]:
    """Rank the whole catalogue by BM25 over the name (Aito's `$similarity`
    lift). No token is required, so partial matches still rank."""
    res = client._request("POST", "/_search", json={
        "from": "products",
        "orderBy": {"$similarity": {"name": q}},
        "select": ["sku"],
        "limit": k,
    })
    return [h["sku"] for h in res.get("hits", [])]


def random_control(skus: list[str]) -> Arm:
    """CONTROL: a seeded random ranking of the catalogue. Its score is the
    CHANCE level every real arm is measured against (see run.py)."""
    def arm(_client: AitoClient, q: str, k: int) -> list[str]:
        ranked = list(skus)
        random.Random(q).shuffle(ranked)
        return ranked[:k]
    return arm
