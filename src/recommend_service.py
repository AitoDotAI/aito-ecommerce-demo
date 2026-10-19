"""For You — personalised tile grid via `_recommend`.

Reuses Smart Search's conversion-KPI shape (ADR 0021) without a search
query, so the result spans every category the persona converts on:
`_recommend product_sku from impressions where {"context.customer": id}
goal {purchased: true}`. Aito learns the persona from their own rows,
never from a profile handed to it (ADR 0033). That retires ADR 0007's
"Olli divergence": his mostly-dog history speaks for itself.
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


PERSONAS: dict[str, Persona] = {
    "maija": Persona("maija", "CUST-00001", "Maija Lehtonen — cat owner"),
    "olli":  Persona("olli",  "CUST-00002", "Olli Mäkelä — multi-pet (small dog)"),
    "saara": Persona("saara", "CUST-00003", "Saara Virtanen — large breed dog owner"),
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
    score: float    # P(purchased | this customer) from Aito's `$p`


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
    #   where:  who is shopping, through the impression's context. Aito
    #           reads the customer from their own rows (ADR 0033).
    #   goal:   the real outcome label `{purchased: true}`.
    #
    # Ranks products by P(purchased | this customer), the textbook
    # personalised recommend; the per-persona flip is learned from the
    # funnel, not asserted (ADR 0021).
    where: dict[str, str] = {"context.customer": persona.customer_id}
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
