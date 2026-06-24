"""For You — personalised tile grid via `_recommend`.

Reuses Smart Search's conversion-KPI shape (ADR 0021) without the
`search_query` filter, so the result spans every category the
persona converts on: `_recommend product_sku from impressions
where {customer_segment, [pet_size]} goal {purchased: true}`.
Persona definitions here override the underlying customer record's
segment for Olli — see ADR 0007 §"Olli divergence" for the why.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, asdict

from src.aito_client import AitoClient
from src import cache


# ── Persona pill bar ──────────────────────────────────────────────


@dataclass(frozen=True)
class Persona:
    persona_id: str        # short id used by the frontend
    customer_id: str       # the underlying CUST-NNNNN
    label: str             # display name (kept aligned with TASK.md)
    segment: str           # the `where.customer_segment` context at query time
    pet_size: str | None   # optional `where.customer_pet_size`


# Olli's segment in the *customer record* is `multi_pet` (ADR 0002 persona),
# but the segment-level conditioning treats `multi_pet` as the whole
# multi-pet population — which leans cat in our fixture. The For You
# goal here uses `dog_owner + small` instead, matching Olli's hand-
# curated personal history (85 % dog). The label stays "multi-pet,
# small dog" per TASK.md; the Aito panel shows the live goal body.
# See `docs/adr/0007-for-you.md` for the rationale.
PERSONAS: dict[str, Persona] = {
    "maija": Persona("maija", "CUST-00001", "Maija Lehtonen — cat owner",
                     segment="cat_owner", pet_size=None),
    "olli":  Persona("olli",  "CUST-00002", "Olli Mäkelä — multi-pet (small dog)",
                     segment="dog_owner", pet_size="small"),
    "saara": Persona("saara", "CUST-00003", "Saara Virtanen — large breed dog owner",
                     segment="dog_owner", pet_size="large"),
}

DEFAULT_PERSONA = "maija"


# ── DTOs ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Tile:
    sku: str
    name: str
    brand: str
    pet_type: str
    category: str
    price_eur: float
    rank: int
    score: float    # P(segment | product) from Aito's `$p`


@dataclass
class ForYouResponse:
    persona: dict
    tiles: list[Tile]
    last_query: dict
    last_response_ms: int

    def to_dict(self) -> dict:
        return {
            "persona":          self.persona,
            "tiles":            [asdict(t) for t in self.tiles],
            "last_query":       self.last_query,
            "last_response_ms": self.last_response_ms,
        }


# ── Live call ─────────────────────────────────────────────────────


def get_for_you(
    client: AitoClient,
    *,
    persona_id: str = DEFAULT_PERSONA,
    limit: int = 12,
) -> ForYouResponse:
    persona = PERSONAS.get(persona_id) or PERSONAS[DEFAULT_PERSONA]

    cache_key = f"for_you:{persona.persona_id}:{limit}"
    cached = cache.get(cache_key)
    if cached:
        return _from_dict(cached)

    # Conversion-KPI recommend over the impressions funnel:
    #
    #   where:  the context — this persona's segment (+ pet_size when
    #           set). The persona signal conditions the probability.
    #   goal:   the real outcome label `{purchased: true}`.
    #
    # Ranks products by P(purchased | this customer's context), the
    # textbook personalised recommend. The per-persona flip is learned
    # from the funnel (cat owners convert on cat products, dog owners
    # on dog) rather than asserted via a segment-affinity proxy. See
    # ADR 0021.
    where: dict[str, str] = {"customer_segment": persona.segment}
    if persona.pet_size is not None:
        where["customer_pet_size"] = persona.pet_size
    goal = {"purchased": True}

    body = {
        "from": "impressions",
        "where": where,
        "recommend": "product_sku",
        "goal": goal,
        "limit": limit,
    }

    started = time.perf_counter()
    res = client.recommend(
        table="impressions",
        where=where,
        recommend_field="product_sku",
        goal=goal,
        limit=limit,
    )
    elapsed = int((time.perf_counter() - started) * 1000)

    tiles: list[Tile] = []
    for idx, hit in enumerate(res.get("hits", []), 1):
        tiles.append(Tile(
            sku=hit.get("sku", ""),
            name=hit.get("name", ""),
            brand=hit.get("brand", ""),
            pet_type=hit.get("pet_type", ""),
            category=hit.get("category", ""),
            price_eur=round(float(hit.get("price_eur", 0)), 2),
            rank=idx,
            score=round(float(hit.get("$p", 0)), 3),
        ))

    resp = ForYouResponse(
        persona={
            "id":          persona.persona_id,
            "label":       persona.label,
            "segment":     persona.segment,
            "pet_size":    persona.pet_size,
            "customer_id": persona.customer_id,
        },
        tiles=tiles,
        last_query={"endpoint": "_recommend", "body": body},
        last_response_ms=elapsed,
    )

    cache.set(cache_key, resp.to_dict(), ttl=300)
    return resp


# ── Cache round-trip ──────────────────────────────────────────────


def _from_dict(d: dict) -> ForYouResponse:
    return ForYouResponse(
        persona=d["persona"],
        tiles=[Tile(**t) for t in d["tiles"]],
        last_query=d["last_query"],
        last_response_ms=d["last_response_ms"],
    )
