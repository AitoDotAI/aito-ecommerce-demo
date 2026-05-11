"""Pattern Explorer — ad-hoc `_relate` over `orders.line_categories`.

Same Aito shape as Bought Together (ADR 0008) but exposes the
**full lift band** — positive, neutral, and protective patterns —
so the user can see what's *not* bought together as well as what
is. The `LiftHint` primitive renders the three bands as green /
grey / red chips.

Cached per anchor for 10 minutes.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, asdict

from src.aito_client import AitoClient
from src import cache

# Re-use Bought Together's anchor catalog + token decoding to keep
# the two views in sync. If a new anchor lands in one view, it
# automatically lands in the other.
from src.bought_together_service import (
    ANCHORS,
    DEFAULT_ANCHOR,
    _humanise,
    _token_to_pair,
)


# ── DTOs ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Pattern:
    label: str
    token: str
    lift: float
    support: dict
    p_given: float
    p_overall: float
    band: str         # "positive" | "neutral" | "protective"


@dataclass
class PatternResponse:
    anchor: dict
    patterns: list[Pattern]
    available_anchors: list[dict]
    last_query: dict
    last_response_ms: int

    def to_dict(self) -> dict:
        return {
            "anchor":          self.anchor,
            "patterns":        [asdict(p) for p in self.patterns],
            "available_anchors": self.available_anchors,
            "last_query":      self.last_query,
            "last_response_ms": self.last_response_ms,
        }


# ── Band classification ───────────────────────────────────────────


def _band(lift: float) -> str:
    if lift >= 1.5:
        return "positive"
    if lift < 0.7:
        return "protective"
    return "neutral"


# ── Live call ─────────────────────────────────────────────────────


def get_patterns(
    client: AitoClient,
    *,
    anchor_id: str = DEFAULT_ANCHOR,
) -> PatternResponse:
    cache_key = f"patterns:{anchor_id}"
    cached = cache.get(cache_key)
    if cached:
        return _from_dict(cached)

    pair = _token_to_pair(anchor_id)
    if pair is None:
        raise ValueError(f"Unknown anchor: {anchor_id!r}")
    pet_type, category = pair

    body = {
        "from": "orders",
        "where": {"line_categories": {"$match": anchor_id}},
        "relate": "line_categories",
        "limit": 30,
    }

    started = time.perf_counter()
    res = client.relate(
        table="orders",
        where=body["where"],
        relate_field="line_categories",
        limit=30,
    )
    elapsed = int((time.perf_counter() - started) * 1000)

    patterns: list[Pattern] = []
    for hit in res.get("hits", []):
        rel = hit.get("related", {}).get("line_categories", {})
        token = rel.get("$has") if isinstance(rel, dict) else None
        if not token or token == anchor_id:
            continue
        lift = float(hit.get("lift", 0))
        decoded = _token_to_pair(token)
        if decoded is None:
            continue
        target_pet, target_cat = decoded
        fs = hit.get("fs", {}) or {}
        ps = hit.get("ps", {}) or {}
        patterns.append(Pattern(
            label=_humanise(target_pet, target_cat),
            token=token,
            lift=round(lift, 2),
            support={
                "f":              int(fs.get("f", 0)),
                "f_on_condition": int(fs.get("fOnCondition", 0)),
            },
            p_given=round(float(ps.get("pOnCondition", 0)), 4),
            p_overall=round(float(ps.get("p", 0)), 4),
            band=_band(lift),
        ))

    # Sort by absolute distance from 1.0 (lift=1 is noise; both
    # very-high and very-low patterns are interesting).
    patterns.sort(key=lambda p: abs(p.lift - 1.0), reverse=True)

    resp = PatternResponse(
        anchor={
            "id":       anchor_id,
            "pet_type": pet_type,
            "category": category,
            "display":  _humanise(pet_type, category),
        },
        patterns=patterns[:20],
        available_anchors=[
            {"id": a.anchor_id, "display": a.display}
            for a in ANCHORS
        ],
        last_query={"endpoint": "_relate", "body": body},
        last_response_ms=elapsed,
    )
    cache.set(cache_key, resp.to_dict(), ttl=600)
    return resp


# ── Cache round-trip ──────────────────────────────────────────────


def _from_dict(d: dict) -> PatternResponse:
    return PatternResponse(
        anchor=d["anchor"],
        patterns=[Pattern(**p) for p in d["patterns"]],
        available_anchors=d["available_anchors"],
        last_query=d["last_query"],
        last_response_ms=d["last_response_ms"],
    )
