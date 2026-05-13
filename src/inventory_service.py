"""Inventory Intelligence — the killer feature of the Operate
section.

Pulls every SKU's current stock + reorder thresholds from the
`inventory` table, joins with the SKU's average monthly demand
from `monthly_sales`, classifies into one of four bands
(critical / low / ok / overstock), and computes cash-impact
figures: tied capital (overstock × unit_cost) and revenue at
risk (critical SKUs' next-month revenue).

Three blocks per request:

  1. KPI strip      — total SKUs, critical, overstock, tied
                       capital € + revenue at risk €
  2. Reorder queue  — critical SKUs sorted by revenue-at-risk
                       descending. Each row has the days-of-supply,
                       suggested reorder quantity, supplier, and
                       a "?" popover with the demand-forecast
                       `$why`.
  3. Overstock list — top tied-capital SKUs (compactly displayed)

Cached for 30 minutes. The reorder queue's per-row `_predict`
for next-month demand is the expensive piece.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict
from typing import Any

from src.aito_client import AitoClient
from src import cache
from src.why_processor import process_estimate_why


# Frozen "today" — every demand forecast is for the NEXT month
# from this anchor. Mirrors `data/generate_fixtures.py`.
DEMO_TODAY_YYYYMM = "2026-04"
FORECAST_MONTH = "2026-05"   # the month we're predicting demand for


# How many critical SKUs to deep-score with a `_predict` call.
# Each predict is ~50 ms — 25 critical × ~50 ms ≈ 1.2 s.
REORDER_TOP_N = 25


# ── DTOs ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Kpi:
    label: str
    value: float
    sub: str


@dataclass(frozen=True)
class ReorderRow:
    sku: str
    name: str
    pet_type: str
    category: str
    current_stock: int
    reorder_point: int
    days_of_supply: float
    avg_monthly_units: int
    forecast_units: int                # predicted next-month units
    suggested_reorder_qty: int          # forecast + safety - current
    unit_cost_eur: float
    revenue_at_risk_eur: float          # forecast × retail × shortfall_fraction
    supplier: str
    lead_time_days: int
    why_explanation: dict | None        # for the per-row "?" popover


@dataclass(frozen=True)
class OverstockRow:
    sku: str
    name: str
    pet_type: str
    category: str
    current_stock: int
    reorder_point: int
    months_of_supply: float
    tied_capital_eur: float
    unit_cost_eur: float


@dataclass
class InventoryResponse:
    kpis: list[Kpi]
    reorder_queue: list[ReorderRow]
    overstock: list[OverstockRow]
    last_query: dict
    last_response_ms: int

    def to_dict(self) -> dict:
        return {
            "kpis":              [asdict(k) for k in self.kpis],
            "reorder_queue":     [asdict(r) for r in self.reorder_queue],
            "overstock":         [asdict(o) for o in self.overstock],
            "last_query":        self.last_query,
            "last_response_ms":  self.last_response_ms,
        }


# ── Helpers ───────────────────────────────────────────────────────


def _band(current: int, reorder_point: int) -> str:
    if current < reorder_point:           return "critical"
    if current < reorder_point * 1.5:     return "low"
    if current > reorder_point * 5:       return "overstock"
    return "ok"


# ── Live calls ─────────────────────────────────────────────────────


def _fetch_all_inventory(client: AitoClient) -> list[dict]:
    """Page through inventory — 658 rows fit in one request, but
    we page anyway to keep the pattern consistent with other
    services."""
    out: list[dict] = []
    offset = 0
    page = 1000
    while True:
        res = client.search("inventory", limit=page, offset=offset)
        hits = res.get("hits", [])
        if not hits:
            break
        out.extend(hits)
        if len(hits) < page:
            break
        offset += page
    return out


def _fetch_products(client: AitoClient) -> dict[str, dict]:
    """SKU → product map (name + price + pet_type + category)."""
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


def _fetch_recent_sales(client: AitoClient) -> dict[str, list[dict]]:
    """SKU → list of recent monthly_sales rows. Powers daily-demand
    arithmetic."""
    out: dict[str, list[dict]] = {}
    offset = 0
    page = 5000
    while True:
        res = client.search("monthly_sales", limit=page, offset=offset)
        hits = res.get("hits", [])
        if not hits:
            break
        for ms in hits:
            out.setdefault(ms["product_sku"], []).append(ms)
        if len(hits) < page:
            break
        offset += page
    return out


def _predict_demand(client: AitoClient, sku: str, sales_history: list[dict]) -> tuple[int, dict | None]:
    """Estimate next-month units_sold for one SKU via `_estimate`.

    Uses `_estimate` (expected-value regression) rather than
    `_predict` because we want the *mean* of next-month units, not
    the most-probable specific integer. Same shape as Demand
    Forecast's `_estimate_units`. See ADR 0015 §"_estimate switch".
    """
    if not sales_history:
        return 0, None
    # Use the most recent row to extract denormalised features.
    recent = max(sales_history, key=lambda r: r["month"])
    forecast_month_int = int(FORECAST_MONTH.split("-")[1])
    season_map = {
        1: "winter", 2: "winter", 3: "spring", 4: "spring",
        5: "spring", 6: "summer", 7: "summer", 8: "summer",
        9: "autumn", 10: "autumn", 11: "autumn", 12: "winter",
    }
    where = {
        "product_sku": sku,
        "month":       FORECAST_MONTH,
        "pet_type":    recent.get("pet_type", ""),
        "category":    recent.get("category", ""),
        "brand":       recent.get("brand", ""),
        "season":      season_map[forecast_month_int],
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


# ── Public entry point ─────────────────────────────────────────────


def get_inventory(
    client: AitoClient,
    *,
    top_n: int = REORDER_TOP_N,
) -> InventoryResponse:
    cached = cache.get("inventory:summary")
    if cached:
        return _from_dict(cached)

    started = time.perf_counter()

    inv_rows = _fetch_all_inventory(client)
    products = _fetch_products(client)
    sales = _fetch_recent_sales(client)

    # Classify every SKU first; we'll deep-score only the critical
    # ones with `_predict` (the expensive call).
    band_counts: dict[str, int] = {"critical": 0, "low": 0, "ok": 0, "overstock": 0}
    classified: list[dict] = []
    for r in inv_rows:
        band = _band(int(r["current_stock"]), int(r["reorder_point"]))
        band_counts[band] += 1
        r2 = dict(r)
        r2["_band"] = band
        classified.append(r2)

    # Tied capital over the whole catalog.
    tied_capital = 0.0
    overstock_rows: list[OverstockRow] = []
    for r in classified:
        if r["_band"] != "overstock":
            continue
        prod = products.get(r["sku"], {})
        excess_units = max(0, int(r["current_stock"]) - int(r["reorder_point"]) * 2)
        tied = excess_units * float(r["unit_cost_eur"])
        tied_capital += tied
        months_supply = (
            int(r["current_stock"]) / max(1, _avg_monthly(sales.get(r["sku"], [])))
        )
        overstock_rows.append(OverstockRow(
            sku=r["sku"],
            name=prod.get("name", r["sku"]),
            pet_type=prod.get("pet_type", ""),
            category=prod.get("category", ""),
            current_stock=int(r["current_stock"]),
            reorder_point=int(r["reorder_point"]),
            months_of_supply=round(months_supply, 1),
            tied_capital_eur=round(tied, 2),
            unit_cost_eur=round(float(r["unit_cost_eur"]), 2),
        ))
    overstock_rows.sort(key=lambda o: -o.tied_capital_eur)
    overstock_rows = overstock_rows[:20]

    # Deep-score critical SKUs with `_predict` (parallel).
    critical = [r for r in classified if r["_band"] == "critical"]
    critical = critical[:top_n]   # cap the predict fan-out

    def score(r: dict) -> tuple[dict, int, dict | None]:
        units, why = _predict_demand(client, r["sku"], sales.get(r["sku"], []))
        return r, units, why

    reorder_rows: list[ReorderRow] = []
    revenue_at_risk_total = 0.0
    if critical:
        with ThreadPoolExecutor(max_workers=8) as pool:
            scored = list(pool.map(score, critical))
        for r, forecast_units, why in scored:
            prod = products.get(r["sku"], {})
            sales_for_sku = sales.get(r["sku"], [])
            avg_monthly = _avg_monthly(sales_for_sku)
            daily = avg_monthly / 30.0
            days_of_supply = (int(r["current_stock"]) / daily) if daily else 0.0
            # Suggested reorder qty: meet next month's forecast +
            # rebuild safety buffer.
            suggested = max(
                0,
                int(forecast_units) + int(r["safety_stock"]) - int(r["current_stock"]),
            )
            # Revenue at risk = forecast units we *can't* satisfy ×
            # retail price.
            shortfall = max(0, int(forecast_units) - int(r["current_stock"]))
            retail = float(prod.get("price_eur", 0) or 0)
            rev_at_risk = shortfall * retail
            revenue_at_risk_total += rev_at_risk
            reorder_rows.append(ReorderRow(
                sku=r["sku"],
                name=prod.get("name", r["sku"]),
                pet_type=prod.get("pet_type", ""),
                category=prod.get("category", ""),
                current_stock=int(r["current_stock"]),
                reorder_point=int(r["reorder_point"]),
                days_of_supply=round(days_of_supply, 1),
                avg_monthly_units=avg_monthly,
                forecast_units=int(forecast_units),
                suggested_reorder_qty=suggested,
                unit_cost_eur=round(float(r["unit_cost_eur"]), 2),
                revenue_at_risk_eur=round(rev_at_risk, 2),
                supplier=str(r.get("supplier", "")),
                lead_time_days=int(r["lead_time_days"]),
                why_explanation=why,
            ))
        reorder_rows.sort(key=lambda x: -x.revenue_at_risk_eur)

    elapsed = int((time.perf_counter() - started) * 1000)

    kpis = [
        Kpi("Total SKUs",       float(len(inv_rows)),        "in stock catalogue"),
        Kpi("Critical",         float(band_counts["critical"]),
            "stock < reorder point"),
        Kpi("Overstock",        float(band_counts["overstock"]),
            "tied capital risk"),
        Kpi("Tied capital",     round(tied_capital, 0),       "€ overstock × cost"),
        Kpi("Revenue at risk",  round(revenue_at_risk_total, 0),
            "€ if criticals stock out"),
    ]

    sample_body = {
        "from": "monthly_sales",
        "where": {
            "product_sku": "<sku>",
            "month":       FORECAST_MONTH,
            "pet_type":    "<from product>",
            "category":    "<from product>",
            "brand":       "<from product>",
            "season":      "spring",
        },
        "estimate": "units_sold",
        "select":   ["estimate", "why"],
    }

    resp = InventoryResponse(
        kpis=kpis,
        reorder_queue=reorder_rows,
        overstock=overstock_rows,
        last_query={"endpoint": "_estimate", "body": sample_body},
        last_response_ms=elapsed,
    )
    cache.set("inventory:summary", resp.to_dict(), ttl=1800)
    return resp


def _avg_monthly(sales: list[dict]) -> int:
    if not sales:
        return 1
    return max(1, int(sum(int(s.get("units_sold", 0)) for s in sales) / len(sales)))


def _from_dict(d: dict) -> InventoryResponse:
    return InventoryResponse(
        kpis=[Kpi(**k) for k in d["kpis"]],
        reorder_queue=[ReorderRow(**r) for r in d["reorder_queue"]],
        overstock=[OverstockRow(**o) for o in d["overstock"]],
        last_query=d["last_query"],
        last_response_ms=d["last_response_ms"],
    )
