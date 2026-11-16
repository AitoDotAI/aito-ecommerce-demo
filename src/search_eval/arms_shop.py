"""Shop-search arms: where do the query words and the shopper's household enter?

Smart Search's right column (`arms.right_blend`) conditions `$p` on the customer
and multiplies it by the name's BM25 lift. It filters nothing, so a cat owner's
"food" can still show dog food. The Shop's search (`src/shop_search.py`) pins the
candidates to every product whose name holds a query word (a list of hundreds of
SKUs) and does not narrow them to the household's pets either.

These arms put the household's pet types in as a candidate filter and vary how the
query words enter (ADR 0066 draft; to be run after 05:30Z, see docs/verification):

  A  list      the Shop's current search: name-matched SKU list, `P x lift`
  B  filter    pet-type filter, one `_search`: `$p x $similarity` (`$multiply`)
  C  evidence  pet-type filter, one `_recommend`: the query as `context.search_query`
               evidence in `$p`, no text lift at all
  D  both      B with the query as `context.search_query` evidence too

The body shapes of B, C and D are UNVERIFIED on 2.12: whether a `product_sku.*`
filter narrows an impressions `_search ... get product_sku` is exactly what the probe
(`tests/test_aito_check.py`-style, local engine) must show before any arm is trusted.
`pets_of` reads the customer's declared pets and fails loudly when there are none.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.aito_client import AitoClient
from src.search_eval.arms import Arm
from src.search_service import PERSONAS, TEXT_THETA

CUSTOMERS_PATH = Path(__file__).resolve().parents[2] / "data" / "customers.json"
# `_name_matches` reads the whole catalogue (658 products); the same bound as the Shop's.
CATALOGUE_LIMIT = 1000


def pets_of(customer_id: str) -> list[str]:
    for customer in json.loads(CUSTOMERS_PATH.read_text()):
        if customer["customer_id"] == customer_id:
            pets = (customer.get("pets") or "").split()
            if not pets:
                raise ValueError(f"{customer_id} declares no pets; the pet-type filter needs them")
            return pets
    raise ValueError(f"No customer {customer_id!r} in {CUSTOMERS_PATH.name}")


def _household_where(customer_id: str, with_query: str | None) -> dict:
    where: dict[str, object] = {"context.customer": customer_id,
                                "product_sku.pet_type": {"$or": pets_of(customer_id)}}
    if with_query is not None:
        where["context.search_query"] = with_query
    return where


def filter_blend_body(q: str, customer_id: str, k: int, *, query_evidence: bool, theta: float = TEXT_THETA) -> dict:
    """B (and D with `query_evidence`): `$p x $similarity` over the household's products."""
    return {"from": "impressions", "get": "product_sku",
            "where": _household_where(customer_id, q if query_evidence else None),
            "orderBy": {"$multiply": [{"$p": {"$context": {"purchased": True}}},
                                      {"$similarity": {"name": q}, "theta": theta}]},
            "select": ["sku"], "limit": k}


def evidence_body(q: str, customer_id: str, k: int) -> dict:
    """C: the household's products ranked by `$p` alone, the query only as context evidence."""
    return {"from": "impressions", "where": _household_where(customer_id, q), "recommend": "product_sku",
            "goal": {"purchased": True}, "select": ["sku"], "limit": k}


def list_body(customer_id: str, skus: list[str]) -> dict:
    """A's `_recommend`: the shopper's `where`, pinned to the name-matched SKUs."""
    return {"from": "impressions",
            "where": {"context.customer": customer_id, "product_sku": {"$or": skus}},
            "recommend": "product_sku", "goal": {"purchased": True}, "select": ["sku", "$p"], "limit": len(skus)}


def arm_list(persona_id: str) -> Arm:
    customer_id = PERSONAS[persona_id].customer_id

    def arm(client: AitoClient, q: str, k: int) -> list[str]:
        named = client.search("products", order_by={"$similarity": {"name": q}, "theta": TEXT_THETA},
                              select=["sku", "$score"], limit=CATALOGUE_LIMIT)
        lift = {h["sku"]: float(h["$score"]) for h in named["hits"] if h["$score"] > 1.0}
        if not lift:
            return []
        hits = client.recommend("impressions", list_body(customer_id, list(lift))["where"], "product_sku",
                                {"purchased": True}, select=["sku", "$p"], limit=len(lift))["hits"]
        return [h["sku"] for h in sorted(hits, key=lambda h: -h["$p"] * lift[h["sku"]])[:k]]
    return arm


def arm_filter(persona_id: str, *, query_evidence: bool) -> Arm:
    customer_id = PERSONAS[persona_id].customer_id

    def arm(client: AitoClient, q: str, k: int) -> list[str]:
        body = filter_blend_body(q, customer_id, k, query_evidence=query_evidence)
        res = client.search(table=body["from"], get=body["get"], where=body["where"], order_by=body["orderBy"],
                            select=body["select"], limit=k)
        return [h["sku"] for h in res["hits"]]
    return arm


def arm_evidence(persona_id: str) -> Arm:
    customer_id = PERSONAS[persona_id].customer_id

    def arm(client: AitoClient, q: str, k: int) -> list[str]:
        body = evidence_body(q, customer_id, k)
        res = client.recommend(body["from"], body["where"], body["recommend"], body["goal"],
                               select=body["select"], limit=k)
        return [h["sku"] for h in res["hits"]]
    return arm


def shop_arms(persona_ids: tuple[str, ...]) -> dict[str, Arm]:
    arms: dict[str, Arm] = {}
    for pid in persona_ids:
        arms[f"shop A list[{pid}]"] = arm_list(pid)
        arms[f"shop B filter x similarity[{pid}]"] = arm_filter(pid, query_evidence=False)
        arms[f"shop C filter + query as evidence[{pid}]"] = arm_evidence(pid)
        arms[f"shop D filter x similarity + evidence[{pid}]"] = arm_filter(pid, query_evidence=True)
    return arms


def on_pet_share(ranked: list[str], pets: list[str], pet_type_of: dict[str, str], k: int = 10) -> float | None:
    """Share of the top k that are the household's own pets' products; None when nothing was returned.
    The judged labels ignore the persona (run.py says so), so this is the personalisation check."""
    top = ranked[:k]
    return sum(pet_type_of[sku] in pets for sku in top) / len(top) if top else None


def household_violations(ranked: list[str], pets: list[str], pet_type_of: dict[str, str], k: int = 10) -> int:
    """Check 1, correct filtering: top-k hits that break the household's pet rule. Must be 0 for an
    arm that claims to filter. (The demo personas declare no diet, so the diet rule has nothing to test here.)"""
    return sum(pet_type_of[sku] not in pets for sku in ranked[:k])


def query_word_misses(ranked: list[str], query: str, name_of: dict[str, str], k: int = 10) -> int:
    """Check 1, correct filtering: top-k hits whose name holds none of the query's words. An arm that ranks
    by `$p` alone (C) can return products the words never named; B and D must not."""
    words = query.lower().split()
    return sum(not any(w in name_of[sku].lower() for w in words) for sku in ranked[:k])


def personas_told_apart(top_by_persona: dict[str, list[str]], k: int = 5) -> bool:
    """Check 2, visibly fit to the profile: the personas' top-k lists for one query are not all the same,
    i.e. the page changes with who is asking. A list ranked without the profile is identical for everyone."""
    return len({tuple(top[:k]) for top in top_by_persona.values()}) > 1
