"""Churn — time-series prediction over the customer_months panel.

The training shape is a panel: one row per customer per month they
were a customer. Each row carries this-month aggregates (visits,
purchases, spent_eur), denormalised profile features (segment,
pet_size, region), tenure-at-this-month, the latest review snapshot
(rating, sentiment, category) and the **forward-looking** target
`churned_in_3_months` — True iff the customer has no orders in the
3 months after this row's month.

Four blocks per request, all live against Aito:

  1. KPI strip       — current totals from the customers table
  2. At-risk         — `_predict churned_in_3_months` per active
                       customer's *latest* customer_month row
  3. Drivers         — `_relate` per profile field over churned
                       customers, tenure bands from `_search` counts
                       (churn_drivers.py)
  4. Accuracy        — one `_evaluate churned_in_3_months` over
                       the panel with the full feature set

See ADR 0013 for the panel-data + forward-label design rationale.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict
from typing import Any

from src.aito_client import AitoClient
from src import cache
from src.churn_drivers import DriverRow, get_churn_drivers
from src.why_processor import process_why


# The cutoff month for "latest customer_month row per customer".
# Matches `DEMO_TODAY_YYYYMM` from the fixture generator — every
# customer has a row at this month.
LATEST_MONTH: str = "2026-04"


# Feature columns Aito conditions on when predicting churn. Mix of
# time-series (visits, purchases, spent_eur), profile (segment,
# region, pet_size, tenure_months_at_month), and latest-review
# (latest_rating, latest_sentiment, latest_category). `month` is
# deliberately excluded — predicting "is this customer about to
# churn" shouldn't read the calendar.
_PREDICT_FEATURES: list[str] = [
    "segment", "pet_size", "region",
    "tenure_months_at_month",
    "visits", "purchases", "spent_eur",
    "latest_rating", "latest_sentiment", "latest_category",
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
    tenure_months: int         # row's tenure_months_at_month
    visits: int                # this month's visits
    purchases: int             # this month's purchases
    spent_eur: float           # this month's spend
    latest_rating: int | None
    latest_sentiment: str | None
    risk_score: float          # P(churned_in_3_months) from Aito
    confidence_band: str       # "high" | "medium" | "low"
    # Processed `$why` for the WhyPopover. None if the row's
    # predict didn't return a $why tree.
    why_explanation: dict | None = None


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
    driver_fields_without_effect: list[str]
    evaluation: EvalSummary
    last_query: dict
    last_response_ms: int

    def to_dict(self) -> dict:
        return {
            "kpis":       [asdict(k) for k in self.kpis],
            "at_risk":    [asdict(a) for a in self.at_risk],
            "drivers":    [asdict(d) for d in self.drivers],
            "driver_fields_without_effect": self.driver_fields_without_effect,
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


def _build_where(row: dict) -> dict:
    """The `where` body for one customer_months row's churn prediction.

    Nullable columns (`pet_size`, `latest_*`) are conditionally
    included — Aito errors on `where: {col: null}`.
    """
    where: dict[str, Any] = {}
    for f in _PREDICT_FEATURES:
        v = row.get(f)
        if v is None:
            continue
        where[f] = v
    return where


# ── Live calls ─────────────────────────────────────────────────────


def _predict_churn_for(client: AitoClient, row: dict) -> tuple[float, dict | None]:
    """P(churned_in_3_months = true) + `$why` decomposition.

    Returns `(score, why_explanation)`. `why_explanation` is the
    processed `$why` tree for the True-class hit (i.e. "why this
    customer might churn"), or None if Aito didn't return a $why.
    """
    res = client.predict(
        table="customer_months",
        where=_build_where(row),
        predict_field="churned_in_3_months",
        limit=2,
    )
    score = 0.0
    why = None
    for hit in res.get("hits", []):
        feature = hit.get("feature")
        if feature is True or feature == "true":
            score = float(hit.get("$p", 0))
            why = process_why(hit.get("$why"), True, actual_p=score)
            break
    return score, why


def _kpi_counts(client: AitoClient) -> list[Kpi]:
    """Point-in-time totals from the customers table.

    The KPI strip reports current state (how many customers, how
    many are churned right now). The forward-looking prediction
    lives on the at-risk leaderboard below.
    """
    total = client.search("customers", limit=0)["total"]
    churned = client.search("customers", where={"churned": True}, limit=0)["total"]
    active = total - churned
    rate_pct = round((churned / total) * 100, 1) if total else 0.0
    return [
        Kpi(label="Total customers", value=total,    sub="cohort size"),
        Kpi(label="Active",          value=active,   sub="ordered in last 90 d"),
        Kpi(label="Churned",         value=churned,  sub="no order in 90 d"),
        Kpi(label="Churn rate",      value=rate_pct, sub="of total cohort"),
    ]


def _at_risk_leaderboard(client: AitoClient, top_n: int) -> list[AtRiskCustomer]:
    """Score active customers' latest customer_month row by P(churn
    in 3 months) and return the top-N.

    `_search where {month: LATEST_MONTH, churned_in_3_months: false}`
    pulls exactly the rows we want to predict on — every active
    customer has a row at the cutoff month with `churned_in_3_months
    = False`. Then N parallel `_predict` calls score each row.
    """
    sample = client.search(
        "customer_months",
        where={"month": LATEST_MONTH, "churned_in_3_months": False},
        limit=top_n * 6,
    ).get("hits", [])
    if not sample:
        return []

    def score(row: dict) -> tuple[dict, float, dict | None]:
        p, why = _predict_churn_for(client, row)
        return row, p, why

    with ThreadPoolExecutor(max_workers=8) as pool:
        scored = list(pool.map(score, sample))

    scored.sort(key=lambda x: -x[1])
    top = scored[:top_n]

    return [
        AtRiskCustomer(
            customer_id=row["customer_id"],
            customer_short=row.get("customer_name") or _short_customer_name(row["customer_id"]),
            segment=row["segment"],
            pet_size=row.get("pet_size"),
            region=row["region"],
            tenure_months=int(row.get("tenure_months_at_month", 0)),
            visits=int(row.get("visits", 0)),
            purchases=int(row.get("purchases", 0)),
            spent_eur=round(float(row.get("spent_eur", 0) or 0), 2),
            latest_rating=row.get("latest_rating"),
            latest_sentiment=row.get("latest_sentiment"),
            risk_score=round(p, 4),
            confidence_band=_confidence_band(p),
            why_explanation=why,
        )
        for row, p, why in top
    ]


def _evaluate_churn(client: AitoClient) -> EvalSummary:
    """One `_evaluate churned_in_3_months` over the panel.

    `$get` reads each held-out row's value at evaluation time.
    Same feature set as the leaderboard's `_predict`.
    """
    where = {
        "segment":                {"$get": "segment"},
        "region":                 {"$get": "region"},
        "tenure_months_at_month": {"$get": "tenure_months_at_month"},
        "visits":                 {"$get": "visits"},
        "purchases":              {"$get": "purchases"},
        "spent_eur":              {"$get": "spent_eur"},
    }
    res = client.evaluate(
        table="customer_months",
        where=where,
        predict_field="churned_in_3_months",
        test_n=300,
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
    # Keyed on the drivers' shape, so an entry cached before the profile
    # drivers (no `driver_fields_without_effect`) is never read back.
    cache_key = f"churn:profile-drivers:{top_n}"
    cached = cache.get(cache_key)
    if cached:
        return _from_dict(cached)

    started = time.perf_counter()
    kpis = _kpi_counts(client)
    at_risk = _at_risk_leaderboard(client, top_n)
    drivers = get_churn_drivers(client)
    evaluation = _evaluate_churn(client)
    elapsed = int((time.perf_counter() - started) * 1000)

    # The "last query" surfaced in the Aito panel is the per-row
    # predict body — it's the load-bearing query and the one a
    # reviewer should inspect.
    sample_body = {
        "from": "customer_months",
        "where": {f: f"<from {f}>" for f in _PREDICT_FEATURES},
        "predict": "churned_in_3_months",
    }

    resp = ChurnResponse(
        kpis=kpis,
        at_risk=at_risk,
        drivers=drivers.drivers,
        driver_fields_without_effect=drivers.fields_without_effect,
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
        driver_fields_without_effect=d["driver_fields_without_effect"],
        evaluation=EvalSummary(**d["evaluation"]),
        last_query=d["last_query"],
        last_response_ms=d["last_response_ms"],
    )
