"""Smart Search — predictive re-ranking.

The demo's headline moment: same query string, side-by-side
results, the right column flips per customer-segment context.
See `docs/adr/0006-smart-search.md` for the chosen query shape +
the denormalisation rationale.

Two live Aito calls per request:
  1. `_search where {name: {$match: q}}`            — baseline
  2. `_recommend product_sku from order_lines
       where {product_sku.name: {$match: q}}
       goal {customer_segment, customer_pet_size}`  — predictive

Cached per `(query, customer_id)` for 5 minutes through the
two-layer cache.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from typing import Iterable

from src.aito_client import AitoClient
from src import cache


# ── Persona pill bar — the three demo customers + their context ────


@dataclass(frozen=True)
class PersonaContext:
    persona_id: str   # short id used by the frontend ("maija", "olli", "saara")
    customer_id: str  # CUST-NNNNN — kept anonymous per CLAUDE.md
    label: str        # display name
    segment: str
    pet_size: str | None


# Olli's customer record is `multi_pet` (per ADR 0002) but the segment
# label averages cat-and-dog across the multi-pet population, which
# erases the per-persona flip in the demo. Aito-side we use his
# *behavioural* segment — `dog_owner + small` — which matches his
# hand-curated 85 %-dog history. The UI label stays "multi-pet, small
# dog" per TASK.md, the Aito panel shows the live goal honestly.
# See `docs/adr/0007-for-you.md` §"Olli divergence".
PERSONAS: dict[str, PersonaContext] = {
    "maija": PersonaContext("maija", "CUST-00001", "Maija — cat owner",
                            segment="cat_owner", pet_size=None),
    "olli":  PersonaContext("olli",  "CUST-00002", "Olli — multi-pet (small dog)",
                            segment="dog_owner", pet_size="small"),
    "saara": PersonaContext("saara", "CUST-00003", "Saara — dog owner (large breed)",
                            segment="dog_owner", pet_size="large"),
}

DEFAULT_PERSONA = "saara"


# ── DTOs ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Hit:
    sku: str
    name: str
    brand: str
    pet_type: str
    category: str
    price_eur: float
    rank: int


@dataclass(frozen=True)
class HitWithDelta:
    sku: str
    name: str
    brand: str
    pet_type: str
    category: str
    price_eur: float
    rank: int
    delta_rank: int | None   # negative = improved
    new_entry: bool          # not in baseline top-N at all


@dataclass
class SmartSearchResponse:
    query: str
    customer: dict
    baseline: list[Hit]
    predictive: list[HitWithDelta]
    last_query: dict
    last_response_ms: int

    def to_dict(self) -> dict:
        return {
            "query":      self.query,
            "customer":   self.customer,
            "baseline":   [asdict(h) for h in self.baseline],
            "predictive": [asdict(h) for h in self.predictive],
            "last_query": self.last_query,
            "last_response_ms": self.last_response_ms,
        }


# ── Live calls ─────────────────────────────────────────────────────


def _baseline_search(client: AitoClient, query: str, limit: int) -> list[Hit]:
    """Plain token-match `_search` — the honest non-predictive baseline."""
    res = client.search(
        table="products",
        where={"name": {"$match": query}},
        limit=limit,
    )
    return [_to_hit(h, idx) for idx, h in enumerate(res.get("hits", []), 1)]


def _predictive_recommend(
    client: AitoClient,
    query: str,
    persona: PersonaContext,
    limit: int,
) -> tuple[list[Hit], dict]:
    """Predictive ranking via `_recommend product_sku`.

    The constraint split:
      - `where` filters rows to matching name tokens AND the
        persona's `customer_pet_size` (when set).
      - `goal` ranks by P(`customer_segment` = persona's segment |
        product = X).

    Multi-field `goal` (`{segment, pet_size}`) has surprising
    semantics for `pet_size=small` — small is shared between small
    dog owners and small multi-pet households (which lean cat),
    and Aito's combined-goal ranking collapses to the cat-heavy
    side. Splitting `pet_size` into `where` lets `goal=segment`
    do its job cleanly. See `docs/aito-cheatsheet.md`.
    """
    where: dict[str, object] = {"product_sku.name": {"$match": query}}
    if persona.pet_size is not None:
        where["customer_pet_size"] = persona.pet_size

    goal = {"customer_segment": persona.segment}

    body = {
        "from": "order_lines",
        "where": where,
        "recommend": "product_sku",
        "goal": goal,
        "limit": limit,
    }
    res = client.recommend(
        table="order_lines",
        where=where,
        recommend_field="product_sku",
        goal=goal,
        limit=limit,
    )
    return [_to_hit(h, idx) for idx, h in enumerate(res.get("hits", []), 1)], body


def _to_hit(raw: dict, rank: int) -> Hit:
    return Hit(
        sku=raw.get("sku", ""),
        name=raw.get("name", ""),
        brand=raw.get("brand", ""),
        pet_type=raw.get("pet_type", ""),
        category=raw.get("category", ""),
        price_eur=round(float(raw.get("price_eur", 0)), 2),
        rank=rank,
    )


def _annotate_with_delta(
    predictive: list[Hit],
    baseline: list[Hit],
) -> list[HitWithDelta]:
    baseline_rank: dict[str, int] = {h.sku: h.rank for h in baseline}
    out: list[HitWithDelta] = []
    for hit in predictive:
        prev = baseline_rank.get(hit.sku)
        if prev is None:
            out.append(HitWithDelta(
                **asdict(hit),
                delta_rank=None,
                new_entry=True,
            ))
        else:
            out.append(HitWithDelta(
                **asdict(hit),
                delta_rank=hit.rank - prev,   # negative => moved UP
                new_entry=False,
            ))
    return out


# ── Public entry point ────────────────────────────────────────────


def smart_search(
    client: AitoClient,
    *,
    query: str,
    persona_id: str = DEFAULT_PERSONA,
    limit: int = 10,
) -> SmartSearchResponse:
    persona = PERSONAS.get(persona_id) or PERSONAS[DEFAULT_PERSONA]

    cache_key = f"smart_search:{persona.persona_id}:{query.lower()}:{limit}"
    cached = cache.get(cache_key)
    if cached:
        return _from_dict(cached)

    started = time.perf_counter()
    baseline = _baseline_search(client, query, limit)
    predictive_hits, last_body = _predictive_recommend(client, query, persona, limit)
    predictive = _annotate_with_delta(predictive_hits, baseline)
    elapsed = int((time.perf_counter() - started) * 1000)

    response = SmartSearchResponse(
        query=query,
        customer={
            "id":      persona.persona_id,
            "label":   persona.label,
            "segment": persona.segment,
            "pet_size": persona.pet_size,
        },
        baseline=baseline,
        predictive=predictive,
        last_query={"endpoint": "_recommend", "body": last_body},
        last_response_ms=elapsed,
    )

    cache.set(cache_key, response.to_dict(), ttl=300)
    return response


# ── Cache round-trip ───────────────────────────────────────────────


def _from_dict(d: dict) -> SmartSearchResponse:
    return SmartSearchResponse(
        query=d["query"],
        customer=d["customer"],
        baseline=[Hit(**h) for h in d["baseline"]],
        predictive=[HitWithDelta(**h) for h in d["predictive"]],
        last_query=d["last_query"],
        last_response_ms=d["last_response_ms"],
    )
