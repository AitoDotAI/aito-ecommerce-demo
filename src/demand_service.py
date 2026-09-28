"""Demand Forecast — per-SKU monthly units prediction.

For each SKU, predict next-month units_sold from the `monthly_sales`
panel. Show the top-volume SKUs with their forecast + lift drivers,
plus seasonality patterns surfaced via `_relate season=summer →
category` and held-out accuracy via `_evaluate`.

Three blocks per request:

  1. Top movers     — top 25 SKUs by avg monthly units, each with
                       a forecast + suggested reorder hint
  2. Seasonality    — `_relate` over `(season, category)` showing
                       which categories peak in which season
  3. Accuracy       — a time-split `_evaluate`, shown next to the
                       naive "same as last month" forecast
                       (see `demand_evaluation.py`)

A failed Aito call raises: the endpoint answers 502 rather than a
page of zero forecasts. Cached 30 min. The 25 parallel `_estimate`
calls are the hot path.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict

from src.aito_client import AitoClient
from src import cache
from src.demand_evaluation import EvalSummary, evaluate_demand
from src.demand_forecast import (
    FORECAST_MONTH, LATEST_MONTH, forecast_units, forecast_where, last_month_units,
)


TOP_N = 25


# ── DTOs ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TopMover:
    sku: str
    name: str
    pet_type: str
    category: str
    avg_monthly_units: int
    last_month_units: int
    forecast_units: int
    forecast_p: float                    # Aito's $p on the top hit
    why_explanation: dict | None


@dataclass(frozen=True)
class SeasonRow:
    season: str
    pet_type: str
    category: str
    lift: float
    f_on_condition: int
    p_on_condition: float
    p_overall: float


@dataclass
class DemandResponse:
    forecast_month: str
    top_movers: list[TopMover]
    seasonality: list[SeasonRow]
    evaluation: EvalSummary
    last_query: dict
    last_response_ms: int

    def to_dict(self) -> dict:
        return {
            "forecast_month":    self.forecast_month,
            "top_movers":        [asdict(t) for t in self.top_movers],
            "seasonality":       [asdict(s) for s in self.seasonality],
            "evaluation":        asdict(self.evaluation),
            "last_query":        self.last_query,
            "last_response_ms":  self.last_response_ms,
        }


# ── Helpers ───────────────────────────────────────────────────────


def _fetch_sales(client: AitoClient) -> list[dict]:
    out: list[dict] = []
    offset = 0
    page = 5000
    while True:
        res = client.search("monthly_sales", limit=page, offset=offset)
        hits = res.get("hits", [])
        if not hits:
            break
        out.extend(hits)
        if len(hits) < page:
            break
        offset += page
    return out


def _fetch_products(client: AitoClient) -> dict[str, dict]:
    out: dict[str, dict] = {}
    offset = 0
    page = 1000
    while True:
        res = client.search("products", limit=page, offset=offset)
        hits = res.get("hits", [])
        if not hits:
            break
        for p in hits:
            out[p["sku"]] = p
        if len(hits) < page:
            break
        offset += page
    return out


def _seasonality(client: AitoClient) -> list[SeasonRow]:
    """`_relate` per season — which categories over-index in each
    season? Parallel calls: spring / summer / autumn / winter.
    """
    seasons = ["spring", "summer", "autumn", "winter"]

    def fetch(season: str) -> tuple[str, dict]:
        res = client.relate(
            table="monthly_sales",
            where={"season": season},
            relate_field="category",
            limit=8,
        )
        return season, res

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(fetch, seasons))

    rows: list[SeasonRow] = []
    for season, res in results:
        for hit in res.get("hits", []):
            rel = hit.get("related", {}).get("category", {})
            value = rel.get("$has") if isinstance(rel, dict) else None
            if value is None:
                continue
            lift = float(hit.get("lift", 0))
            if abs(lift - 1.0) < 0.08:
                continue
            ps = hit.get("ps", {}) or {}
            fs = hit.get("fs", {}) or {}
            rows.append(SeasonRow(
                season=season,
                pet_type="",   # not in this query; left blank
                category=str(value),
                lift=round(lift, 2),
                f_on_condition=int(fs.get("fOnCondition", 0)),
                p_on_condition=round(float(ps.get("pOnCondition", 0)), 4),
                p_overall=round(float(ps.get("p", 0)), 4),
            ))
    rows.sort(key=lambda r: -abs(r.lift - 1.0))
    return rows[:12]


# ── Public entry point ─────────────────────────────────────────────


def get_demand(
    client: AitoClient,
    *,
    top_n: int = TOP_N,
) -> DemandResponse:
    cached = cache.get(f"demand:{top_n}:{FORECAST_MONTH}")
    if cached:
        return _from_dict(cached)

    started = time.perf_counter()

    sales = _fetch_sales(client)
    products = _fetch_products(client)

    # Aggregate per-SKU stats from monthly_sales.
    by_sku: dict[str, list[dict]] = {}
    for s in sales:
        by_sku.setdefault(s["product_sku"], []).append(s)

    # Sort SKUs by average monthly units (descending) — that's the
    # top-movers list.
    movers = sorted(by_sku.items(),
                    key=lambda item: -sum(r["units_sold"] for r in item[1]) / len(item[1]))[:top_n]

    # Parallel _estimate for next month per SKU.
    with ThreadPoolExecutor(max_workers=8) as pool:
        forecasts = list(pool.map(lambda item: forecast_units(client, *item), movers))

    top_movers: list[TopMover] = []
    for (sku, rows), (units, why) in zip(movers, forecasts):
        latest = max(rows, key=lambda r: r["month"])
        top_movers.append(TopMover(
            sku=sku,
            name=products[sku]["name"],
            pet_type=latest["pet_type"],
            category=latest["category"],
            avg_monthly_units=round(sum(r["units_sold"] for r in rows) / len(rows)),
            last_month_units=last_month_units(rows),
            forecast_units=units,
            forecast_p=0.0,   # _estimate returns expected value, not a probability
            why_explanation=why,
        ))

    seasonality = _seasonality(client)
    evaluation = evaluate_demand(client, LATEST_MONTH)

    elapsed = int((time.perf_counter() - started) * 1000)

    # The body actually sent for the first top mover, not a lookalike.
    first_sku, first_rows = movers[0]
    sample_body = {
        "from": "monthly_sales",
        "where": forecast_where(first_sku, max(first_rows, key=lambda r: r["month"]),
                                last_month_units(first_rows)),
        "estimate": "units_sold",
        "select":   ["estimate", "why"],
    }

    resp = DemandResponse(
        forecast_month=FORECAST_MONTH,
        top_movers=top_movers,
        seasonality=seasonality,
        evaluation=evaluation,
        last_query={"endpoint": "_estimate", "body": sample_body},
        last_response_ms=elapsed,
    )
    cache.set(f"demand:{top_n}:{FORECAST_MONTH}", resp.to_dict(), ttl=1800)
    return resp


def _from_dict(d: dict) -> DemandResponse:
    return DemandResponse(
        forecast_month=d["forecast_month"],
        top_movers=[TopMover(**t) for t in d["top_movers"]],
        seasonality=[SeasonRow(**s) for s in d["seasonality"]],
        evaluation=EvalSummary(**d["evaluation"]),
        last_query=d["last_query"],
        last_response_ms=d["last_response_ms"],
    )
