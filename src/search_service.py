"""Smart Search — text relevance, and text relevance x purchase probability.

The demo's headline moment: same query string, side-by-side
results, the right column flips per customer-segment context.

Two live Aito calls per request (ADR 0026, step 1):
  1. baseline   — `_search products` ordered by `$similarity` over the
                  name (BM25). Rows that match no query word are dropped.
  2. predictive — `_search impressions get product_sku`, ordered by
                  `$multiply [$p{purchased} , $similarity name]`: purchase
                  probability for this customer context x text match, over
                  the whole catalogue in one query.

Neither column filters candidates on the query words. The previous
`name $match` filter required EVERY word in the name, so natural
phrasing ("food for an old dog"), misspellings and Finnish/Swedish
queries returned nothing in both columns. Measured on the judged query
set (`./do search-eval`, docs/verification/search-eval.md).

Cached per `(query, customer_id)` for 5 minutes through the
two-layer cache.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
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
    "maija": PersonaContext("maija", "CUST-00001", "Maija Lehtonen — cat owner",
                            segment="cat_owner", pet_size=None),
    "olli":  PersonaContext("olli",  "CUST-00002", "Olli Mäkelä — multi-pet (small dog)",
                            segment="dog_owner", pet_size="small"),
    "saara": PersonaContext("saara", "CUST-00003", "Saara Virtanen — dog owner (large breed)",
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
    # False when no product name contains any query word. The predictive
    # column then ranks on purchase probability alone, and the page must
    # say so rather than present it as a text match.
    text_matched: bool
    last_query: dict
    last_response_ms: int

    def to_dict(self) -> dict:
        return {
            "query":      self.query,
            "customer":   self.customer,
            "baseline":   [asdict(h) for h in self.baseline],
            "predictive": [asdict(h) for h in self.predictive],
            "text_matched": self.text_matched,
            "last_query": self.last_query,
            "last_response_ms": self.last_response_ms,
        }


# ── Live calls ─────────────────────────────────────────────────────


PRODUCT_FIELDS = ["sku", "name", "brand", "pet_type", "category", "price_eur"]

# The text arm's weight in the predictive blend. Aito's calibrated default
# is 0.33; on the judged query set it let purchase probability drown the
# words (a cat owner asking for "food for an old dog" got cat food, nDCG@10
# 0.31). At 2.0 relevance matched BM25, but a cat owner's "dog food" still
# had cat food at ranks 7-10. 3.0 is the smallest weight tried that keeps a
# pet-specific query on that pet (tests/test_aito_check.py) while the
# customer still decides ambiguous queries like "food". Every weight tried
# is scored in docs/verification/search-eval.md.
TEXT_THETA = 3.0


def _baseline_search(client: AitoClient, query: str, limit: int) -> list[Hit]:
    """BM25 over the product name — the honest non-predictive baseline.

    `$score` is the lift `exp(θ·bm25)`: exactly 1.0 means no query word
    matched. Those rows are dropped rather than shown, because they come
    back in table order — the first ten dog foods, whatever was typed.
    """
    res = client.search(
        table="products",
        order_by={"$similarity": {"name": query}},
        select=PRODUCT_FIELDS + ["$score"],
        limit=limit,
    )
    matched = [h for h in res["hits"] if h["$score"] > 1.0]
    return [_to_hit(h, idx) for idx, h in enumerate(matched, 1)]


def predictive_blend_body(query: str, persona: PersonaContext, limit: int,
                          text_theta: float = TEXT_THETA) -> dict:
    """The predictive column's `_search` body, shared with the search
    evaluation so the harness measures exactly what the page runs.

    - `from impressions, get product_sku`: `where` and `$p` read the
      impressions funnel; the rows returned are products.
    - `where`: the customer context to condition on (segment, pet size).
    - `$p{$context: {purchased: true}}`: P(this context buys the product).
    - `$similarity {name: query}`: BM25 over the product name, as a lift.
    - `$multiply`: rank by the product of the two. A product that matches
      no query word keeps lift 1.0, so it can still rank on purchase
      probability alone — relevant when the words fail (a misspelling),
      beaten whenever something matches them.

    The selected `$p` would be the blended score, not a probability, so it
    is not selected.
    """
    where: dict[str, object] = {"customer_segment": persona.segment}
    if persona.pet_size is not None:
        where["customer_pet_size"] = persona.pet_size
    return {
        "from": "impressions",
        "get": "product_sku",
        "where": where,
        "orderBy": {"$multiply": [
            {"$p": {"$context": {"purchased": True}}},
            {"$similarity": {"name": query}, "theta": text_theta},
        ]},
        "select": PRODUCT_FIELDS,
        "limit": limit,
    }


def _predictive_blend(
    client: AitoClient,
    query: str,
    persona: PersonaContext,
    limit: int,
) -> tuple[list[Hit], dict]:
    body = predictive_blend_body(query, persona, limit)
    res = client.search(
        table=body["from"],
        get=body["get"],
        where=body["where"],
        order_by=body["orderBy"],
        select=body["select"],
        limit=body["limit"],
    )
    return [_to_hit(h, idx) for idx, h in enumerate(res["hits"], 1)], body


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
    # The two Aito calls are independent — run them in parallel so
    # cold wall-clock is max(baseline, predictive) rather than the sum.
    with ThreadPoolExecutor(max_workers=2) as pool:
        baseline_fut = pool.submit(_baseline_search, client, query, limit)
        predictive_fut = pool.submit(
            _predictive_blend, client, query, persona, limit
        )
        baseline = baseline_fut.result()
        predictive_hits, last_body = predictive_fut.result()
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
        # The baseline is BM25 over the same name field with non-matching
        # rows dropped, so it is empty exactly when no name matches a word.
        text_matched=bool(baseline),
        last_query={"endpoint": "_search", "body": last_body},
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
        text_matched=d["text_matched"],
        last_query=d["last_query"],
        last_response_ms=d["last_response_ms"],
    )
