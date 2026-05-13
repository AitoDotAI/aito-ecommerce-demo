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
  3. Accuracy       — one `_evaluate units_sold` over a 300-row
                       held-out monthly_sales sample

Cached 30 min. The 25 parallel `_predict` calls are the hot path.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict

from src.aito_client import AitoClient
from src import cache
from src.why_processor import process_estimate_why


FORECAST_MONTH = "2026-05"   # the month we predict for
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


@dataclass(frozen=True)
class EvalSummary:
    accuracy: float
    base_accuracy: float
    accuracy_gain_pp: float
    n: int


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


_SEASON_BY_MONTH = {
    1: "winter", 2: "winter", 3: "spring", 4: "spring",
    5: "spring", 6: "summer", 7: "summer", 8: "summer",
    9: "autumn", 10: "autumn", 11: "autumn", 12: "winter",
}


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


def _estimate_units(client: AitoClient, sku: str, recent: dict, month: str) -> tuple[int, dict | None]:
    """`_estimate units_sold` for one SKU + month. Returns the
    expected units (rounded) and the popover-shaped why payload.

    Switched from `_predict` to `_estimate` because the question is
    "what's the expected number of units" (continuous regression),
    not "what's the most-probable integer count" (discrete
    classification). `_estimate` returns a single mean; `_predict`
    on an Int column returns ranked specific values with low per-
    value probabilities.

    See aito-demo's `src/12-price-estimation.js` for the canonical
    `_estimate` pattern this mirrors.
    """
    month_int = int(month.split("-")[1])
    where = {
        "product_sku": sku,
        "month":       month,
        "pet_type":    recent.get("pet_type", ""),
        "category":    recent.get("category", ""),
        "brand":       recent.get("brand", ""),
        "season":      _SEASON_BY_MONTH[month_int],
    }
    try:
        res = client.estimate("monthly_sales", where=where,
                              estimate_field="units_sold")
    except Exception:
        return 0, None
    estimate = res.get("estimate")
    if estimate is None:
        return 0, None
    units = max(0, int(round(float(estimate))))
    why = process_estimate_why(
        res.get("why"), float(estimate),
        field_label="units_sold",
    )
    return units, why


def _seasonality(client: AitoClient) -> list[SeasonRow]:
    """`_relate` per season — which categories over-index in each
    season? Parallel calls: spring / summer / autumn / winter.
    """
    seasons = ["spring", "summer", "autumn", "winter"]

    def fetch(season: str) -> tuple[str, dict]:
        try:
            res = client.relate(
                table="monthly_sales",
                where={"season": season},
                relate_field="category",
                limit=8,
            )
        except Exception:
            return season, {}
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


def _evaluate_demand(client: AitoClient) -> EvalSummary:
    where = {
        "product_sku": {"$get": "product_sku"},
        "month":       {"$get": "month"},
        "pet_type":    {"$get": "pet_type"},
        "category":    {"$get": "category"},
        "brand":       {"$get": "brand"},
        "season":      {"$get": "season"},
    }
    try:
        res = client.evaluate(
            table="monthly_sales",
            where=where,
            predict_field="units_sold",
            test_limit=300,
        )
    except Exception:
        return EvalSummary(0.0, 0.0, 0.0, 0)
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
    sku_stats: list[tuple[str, float, int, dict]] = []
    for sku, rows in by_sku.items():
        avg = sum(int(r.get("units_sold", 0)) for r in rows) / len(rows)
        latest = max(rows, key=lambda r: r["month"])
        last_units = int(latest.get("units_sold", 0))
        sku_stats.append((sku, avg, last_units, latest))
    sku_stats.sort(key=lambda t: -t[1])
    sku_stats = sku_stats[:top_n]

    # Parallel _estimate for next month per SKU.
    def estimate_one(t):
        sku, avg, last_units, latest = t
        units, why = _estimate_units(client, sku, latest, FORECAST_MONTH)
        return sku, avg, last_units, latest, units, why

    with ThreadPoolExecutor(max_workers=8) as pool:
        scored = list(pool.map(estimate_one, sku_stats))

    top_movers: list[TopMover] = []
    for sku, avg, last_units, latest, forecast_units, why in scored:
        prod = products.get(sku, {})
        top_movers.append(TopMover(
            sku=sku,
            name=prod.get("name", sku),
            pet_type=latest.get("pet_type", ""),
            category=latest.get("category", ""),
            avg_monthly_units=int(round(avg)),
            last_month_units=last_units,
            forecast_units=int(forecast_units),
            forecast_p=0.0,   # _estimate returns expected value, not a probability
            why_explanation=why,
        ))

    seasonality = _seasonality(client)
    evaluation = _evaluate_demand(client)

    elapsed = int((time.perf_counter() - started) * 1000)

    sample_body = {
        "from": "monthly_sales",
        "where": {
            "product_sku": "<sku>",
            "month":       FORECAST_MONTH,
            "pet_type":    "<from monthly_sales row>",
            "category":    "<from monthly_sales row>",
            "brand":       "<from monthly_sales row>",
            "season":      "spring",
        },
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
