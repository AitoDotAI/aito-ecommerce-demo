"""Churn — the killer feature of the Understand section.

A customer counts as **churned** when their last order is in or
before `2026-01` (90 days before frozen demo today = 2026-04). The
label is deterministic at fixture-gen time; this service surfaces
Aito's *prediction* of that label off feature-only conditioning
(segment, pet_size, region, tenure, total_orders, total_spent_eur)
— i.e. predicting churn *without* using the timestamp.

Four blocks per request, all live against Aito:

  1. KPI strip      — `_search limit=0` for total / churned / active
  2. At-risk        — `_predict churned` in parallel for a sample of
                       active customers, ranked by P(churned=true)
  3. Drivers        — three parallel `_relate` calls (segment /
                       region / pet_size) where `churned=true`,
                       returning lift per value
  4. Accuracy       — one `_evaluate churned` over a 200-row sample

Cached for 30 minutes — the predict fan-out is the load-bearing
cost, ~2 s warm.

See ADR 0013 for the design rationale + feature-set choice.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict
from typing import Any

from src.aito_client import AitoClient
from src import cache


# Features Aito sees for the churn prediction. Deliberately excludes
# `last_order_month` — that would let Aito read the timestamp and
# perfectly predict the deterministic label. The demo's narrative is
# "predict churn from who they are, not from when they last ordered".
_PREDICT_FEATURES: list[str] = [
    "segment", "pet_size", "region",
    "tenure_months", "total_orders", "total_spent_eur",
]


# ── DTOs ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Kpi:
    label: str
    value: int | float
    sub: str


@dataclass(frozen=True)
class AtRiskCustomer:
    customer_id: str
    customer_short: str        # "Mikko T."
    segment: str
    pet_size: str | None
    region: str
    tenure_months: int
    total_orders: int
    total_spent_eur: float
    last_order_month: str | None
    risk_score: float          # P(churned=true) from Aito
    confidence_band: str       # "high" | "medium" | "low"


@dataclass(frozen=True)
class DriverRow:
    field: str                 # "segment", "region", "pet_size"
    value: str                 # the specific value, e.g. "small_animal_owner"
    lift: float                # lift of P(churned | this value) vs baseline
    support_f: int             # number of churned customers with this value
    p_churn: float             # P(churned | this value)
    p_overall: float           # P(churned) across all customers


@dataclass(frozen=True)
class EvalSummary:
    accuracy: float
    base_accuracy: float
    accuracy_gain_pp: float
    n: int


@dataclass
class ChurnResponse:
    kpis: list[Kpi]
    at_risk: list[AtRiskCustomer]
    drivers: list[DriverRow]
    evaluation: EvalSummary
    last_query: dict
    last_response_ms: int

    def to_dict(self) -> dict:
        return {
            "kpis":       [asdict(k) for k in self.kpis],
            "at_risk":    [asdict(a) for a in self.at_risk],
            "drivers":    [asdict(d) for d in self.drivers],
            "evaluation": asdict(self.evaluation),
            "last_query":       self.last_query,
            "last_response_ms": self.last_response_ms,
        }


# ── Helpers ───────────────────────────────────────────────────────


_FIRST_NAMES = [
    "Mikko", "Sari", "Antti", "Maija", "Olli", "Saara", "Liisa", "Janne",
    "Heidi", "Pekka", "Maria", "Joonas", "Erika", "Henrik", "Petra",
]


def _short_customer_name(customer_id: str) -> str:
    """Mirror of `overview_service._short_customer_name` so the
    recent-orders + at-risk lists share the same anonymous labels."""
    h = sum(ord(c) for c in customer_id)
    first = _FIRST_NAMES[h % len(_FIRST_NAMES)]
    initial = chr(ord("A") + ((h // 7) % 26))
    return f"{first} {initial}."


def _confidence_band(p: float) -> str:
    if p >= 0.70:
        return "high"
    if p >= 0.45:
        return "medium"
    return "low"


def _build_where(customer: dict) -> dict:
    """The `where` for one customer's churn prediction.

    Uses only the feature columns (`_PREDICT_FEATURES`). `pet_size`
    is conditionally included because it's nullable — cat-owner /
    aquarium-owner rows don't have one and Aito errors on
    `None`-valued where keys.
    """
    where: dict[str, Any] = {}
    for f in _PREDICT_FEATURES:
        if f == "pet_size":
            if customer.get("pet_size"):
                where["pet_size"] = customer["pet_size"]
            continue
        where[f] = customer[f]
    return where


# ── Live calls ─────────────────────────────────────────────────────


def _predict_churn_for(client: AitoClient, customer: dict) -> float:
    """Per-customer churn probability via `_predict churned`.

    Returns P(churned=true). Aito returns hits ranked by `$p`;
    we read the hit whose `feature` is `True`.
    """
    res = client.predict(
        table="customers",
        where=_build_where(customer),
        predict_field="churned",
        limit=2,
    )
    for hit in res.get("hits", []):
        if hit.get("feature") is True or hit.get("feature") == "true":
            return float(hit.get("$p", 0))
    return 0.0


def _kpi_counts(client: AitoClient) -> tuple[list[Kpi], int]:
    total    = client.search("customers", limit=0)["total"]
    churned  = client.search("customers", where={"churned": True}, limit=0)["total"]
    active   = total - churned
    rate_pct = round((churned / total) * 100, 1) if total else 0.0
    kpis = [
        Kpi(label="Total customers",   value=total,   sub="cohort size"),
        Kpi(label="Active",            value=active,  sub="ordered in last 90 d"),
        Kpi(label="Churned",           value=churned, sub="no order in 90 d"),
        Kpi(label="Churn rate",        value=rate_pct, sub="of total cohort"),
    ]
    return kpis, active


def _at_risk_leaderboard(client: AitoClient, top_n: int) -> list[AtRiskCustomer]:
    """Sample active customers, score each, return the top-N by risk.

    Samples ~5× top_n customers so the leaderboard reads the *real*
    top of the distribution, not just the first few sampled. Predict
    calls run in a thread pool capped at 8 — `_predict` is ~50 ms each
    and Aito tolerates the small concurrency without complaint.
    """
    sample_size = top_n * 5
    sample = client.search(
        "customers",
        where={"churned": False},
        limit=sample_size,
    ).get("hits", [])

    if not sample:
        return []

    def score(cust: dict) -> tuple[dict, float]:
        return cust, _predict_churn_for(client, cust)

    with ThreadPoolExecutor(max_workers=8) as pool:
        scored = list(pool.map(score, sample))

    scored.sort(key=lambda x: -x[1])
    top = scored[:top_n]
    return [
        AtRiskCustomer(
            customer_id=c["customer_id"],
            customer_short=_short_customer_name(c["customer_id"]),
            segment=c["segment"],
            pet_size=c.get("pet_size"),
            region=c["region"],
            tenure_months=int(c["tenure_months"]),
            total_orders=int(c["total_orders"]),
            total_spent_eur=round(float(c["total_spent_eur"]), 2),
            last_order_month=c.get("last_order_month"),
            risk_score=round(p, 4),
            confidence_band=_confidence_band(p),
        )
        for c, p in top
    ]


def _drivers(client: AitoClient) -> list[DriverRow]:
    """Three parallel `_relate` calls — one per discrete feature.

    Each returns lift of P(churned | field=value) vs baseline. We
    merge the three result sets, drop neutral lifts, sort by lift
    descending, take the top 8.
    """
    relate_fields = ["segment", "region", "pet_size"]

    def fetch(field: str) -> tuple[str, dict]:
        try:
            res = client.relate(
                table="customers",
                where={"churned": True},
                relate_field=field,
                limit=10,
            )
        except Exception:
            return field, {}
        return field, res

    with ThreadPoolExecutor(max_workers=len(relate_fields)) as pool:
        results = list(pool.map(fetch, relate_fields))

    rows: list[DriverRow] = []
    for field, res in results:
        for hit in res.get("hits", []):
            rel = hit.get("related", {}).get(field, {})
            value = rel.get("$is") if isinstance(rel, dict) else None
            if value is None:
                continue
            lift = float(hit.get("lift", 0))
            if abs(lift - 1.0) < 0.15:
                continue   # neutral — not a driver
            ps = hit.get("ps", {}) or {}
            fs = hit.get("fs", {}) or {}
            rows.append(DriverRow(
                field=field,
                value=str(value),
                lift=round(lift, 2),
                support_f=int(fs.get("fOnCondition", 0)),
                p_churn=round(float(ps.get("pOnCondition", 0)), 4),
                p_overall=round(float(ps.get("p", 0)), 4),
            ))

    rows.sort(key=lambda r: -r.lift)
    return rows[:8]


def _evaluate_churn(client: AitoClient) -> EvalSummary:
    """One `_evaluate churned` over a 200-row sample.

    The `where` reads each held-out row's features via `$get`. We
    exclude `last_order_month` for the same reason the prediction
    does — otherwise the timestamp leaks the deterministic label.
    """
    where = {
        "segment":        {"$get": "segment"},
        "region":         {"$get": "region"},
        "tenure_months":  {"$get": "tenure_months"},
        "total_orders":   {"$get": "total_orders"},
        "total_spent_eur": {"$get": "total_spent_eur"},
    }
    res = client.evaluate(
        table="customers",
        where=where,
        predict_field="churned",
        test_limit=200,
    )
    accuracy = float(res.get("accuracy", 0) or 0)
    base = float(res.get("baseAccuracy", 0) or 0)
    gain = float(res.get("accuracyGain", accuracy - base) or 0)
    return EvalSummary(
        accuracy=round(accuracy, 4),
        base_accuracy=round(base, 4),
        accuracy_gain_pp=round(gain * 100, 2),
        n=int(res.get("n", 0)),
    )


# ── Public entry point ─────────────────────────────────────────────


def get_churn(
    client: AitoClient,
    *,
    top_n: int = 20,
) -> ChurnResponse:
    """Compose the full Churn payload. Cached for 30 minutes."""
    cache_key = f"churn:{top_n}"
    cached = cache.get(cache_key)
    if cached:
        return _from_dict(cached)

    started = time.perf_counter()
    kpis, _active = _kpi_counts(client)
    at_risk = _at_risk_leaderboard(client, top_n)
    drivers = _drivers(client)
    evaluation = _evaluate_churn(client)
    elapsed = int((time.perf_counter() - started) * 1000)

    # The "last query" shown in the Aito panel is the per-customer
    # predict body — it's the load-bearing query and the one a
    # reviewer wants to inspect. The drivers + evaluate are
    # secondary.
    sample_body = {
        "from": "customers",
        "where": {
            f: "<from customer row>"
            for f in _PREDICT_FEATURES
        },
        "predict": "churned",
    }

    resp = ChurnResponse(
        kpis=kpis,
        at_risk=at_risk,
        drivers=drivers,
        evaluation=evaluation,
        last_query={"endpoint": "_predict", "body": sample_body},
        last_response_ms=elapsed,
    )
    cache.set(cache_key, resp.to_dict(), ttl=1800)
    return resp


# ── Cache round-trip ──────────────────────────────────────────────


def _from_dict(d: dict) -> ChurnResponse:
    return ChurnResponse(
        kpis=[Kpi(**k) for k in d["kpis"]],
        at_risk=[AtRiskCustomer(**a) for a in d["at_risk"]],
        drivers=[DriverRow(**dr) for dr in d["drivers"]],
        evaluation=EvalSummary(**d["evaluation"]),
        last_query=d["last_query"],
        last_response_ms=d["last_response_ms"],
    )
