"""Markdown decision view — what to discount, by how much, and the
revenue recovery that follows.

Ties three things the demo already computes into one workflow:

  - Overstock SKUs from the Inventory view (current_stock > 2 ×
    reorder_point) — the input pile.
  - Per-SKU unit_cost from the same `inventory` table — the floor
    that says how deep a discount can go before margin disappears.
  - Aito's `_estimate units_sold` at several markdown levels (from
    the Price view) — the demand response that turns a price cut
    into more units / faster clearance.

Output: for each overstock SKU, the markdown depth that maximises
"recoverable revenue" (price × units − cost × units) subject to
the soft constraint "clear ≥ 70 % of excess stock in 90 days".
The KPI strip rolls these up to give the merchandiser one number:
"€X tied capital, €Y recoverable at proposed markdowns".

Cached for 30 minutes.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict
from typing import Any

from src.aito_client import AitoClient
from src import cache


# Same anchor as Inventory / Price. The markdown horizon is "the
# next 3 months from today" — long enough to clear at most retail
# discounts, short enough that the merchandiser cares.
DEMO_TODAY_YYYYMM = "2026-04"
CLEAR_HORIZON_MONTHS = 3

# Discount levels Aito's `_estimate` is probed at. Same range the
# Price view uses, so the inputs match the customer-facing curve.
MARKDOWN_LEVELS_PCT: list[int] = [0, 5, 10, 15, 20]

# Top-N overstock SKUs to deep-score. Each SKU runs 5 parallel
# `_estimate` calls; 15 SKUs × 5 = 75 calls, comfortable under
# Aito's inFlightWeight ceiling.
MARKDOWN_TOP_N = 15

# Soft clearance target — propose the deepest markdown only if it
# clears ≥ this fraction of excess in 90 days. Keeps the view from
# recommending implausibly small markdowns just because they
# preserve unit margin.
TARGET_CLEAR_FRACTION = 0.70


# ── DTOs ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class MarkdownCurvePoint:
    """One row of the per-SKU markdown sweep — shown in the row's
    detail popover so the merchandiser can see why the chosen
    discount won."""
    discount_pct: int          # 0, 5, 10, 15, 20
    price_eur: float
    monthly_units: float       # Aito's `_estimate` at this price
    weeks_to_clear: float      # excess_stock / weekly_units
    margin_per_unit_eur: float # price − unit_cost
    recoverable_revenue_eur: float  # (price − cost) × cleared_units


@dataclass(frozen=True)
class MarkdownRow:
    sku: str
    name: str
    pet_type: str
    category: str
    current_stock: int
    reorder_point: int
    list_price_eur: float
    unit_cost_eur: float
    excess_units: int                     # stock − 2 × reorder_point
    tied_capital_eur: float               # excess × unit_cost
    proposed_discount_pct: int            # the chosen markdown
    proposed_price_eur: float
    proposed_weeks_to_clear: float
    proposed_recoverable_revenue_eur: float
    proposed_margin_lost_eur: float       # (list − chosen) × cleared_units
    curve: list[MarkdownCurvePoint]       # the full sweep, for transparency


@dataclass(frozen=True)
class Kpi:
    label: str
    value: float
    sub: str


@dataclass
class MarkdownResponse:
    kpis: list[Kpi]
    proposals: list[MarkdownRow]
    last_query: dict
    last_response_ms: int

    def to_dict(self) -> dict:
        return {
            "kpis":             [asdict(k) for k in self.kpis],
            "proposals":        [asdict(p) for p in self.proposals],
            "last_query":       self.last_query,
            "last_response_ms": self.last_response_ms,
        }


# ── Helpers ───────────────────────────────────────────────────────


def _is_overstock(current: int, reorder_point: int) -> bool:
    return current > reorder_point * 5


def _avg_monthly_units(sales: list[dict]) -> float:
    """Mean units sold per month from the SKU's recent sales rows.
    Anchor for the demand-curve baseline when Aito's `_estimate`
    doesn't have a recent observation at that price."""
    if not sales:
        return 0.0
    return sum(int(s.get("units_sold", 0) or 0) for s in sales) / len(sales)


_SEASON_BY_MONTH = {
    1: "winter", 2: "winter", 3: "spring", 4: "spring",
    5: "spring", 6: "summer", 7: "summer", 8: "summer",
    9: "autumn", 10: "autumn", 11: "autumn", 12: "winter",
}


def _estimate_at_price(
    client: AitoClient,
    sku: str,
    base_price: float,
    discount_pct: int,
    recent: dict,
    forecast_month: str,
) -> tuple[float, float]:
    """Run `_estimate units_sold` for one (SKU, price) point.

    Returns (adjusted_price, expected_monthly_units). Same shape as
    Price view's `_estimate_one_curve_point` — kept separate so the
    two views can evolve independently.
    """
    adjusted = round(base_price * (1.0 - discount_pct / 100.0), 2)
    where = {
        "product_sku": sku,
        "month":       forecast_month,
        "pet_type":    recent.get("pet_type", ""),
        "category":    recent.get("category", ""),
        "brand":       recent.get("brand", ""),
        "season":      _SEASON_BY_MONTH[int(forecast_month.split("-")[1])],
        "price_eur":   adjusted,
    }
    try:
        res = client.estimate("monthly_sales", where=where,
                              estimate_field="units_sold", with_why=False)
    except Exception:
        return adjusted, 0.0
    estimate = res.get("estimate")
    if estimate is None:
        return adjusted, 0.0
    return adjusted, max(0.0, float(estimate))


def _pick_best_markdown(curve: list[MarkdownCurvePoint]) -> MarkdownCurvePoint:
    """Pick the discount that maximises recoverable revenue across
    the clearance horizon, with a soft preference for clearing ≥
    TARGET_CLEAR_FRACTION of excess in 90 days.

    Ties are broken toward shallower discounts (less margin given
    up) — keeps the view from over-recommending deep cuts when a
    light promo would do the job.
    """
    # Filter to discounts that clear excess in the horizon (≈ 13 weeks).
    # Among those, max recoverable revenue wins; if none qualify, pick
    # the discount that clears fastest — honest signal that "this SKU
    # won't clear at ≤ 20 % off; consider deeper markdown or liquidation".
    target_weeks = (CLEAR_HORIZON_MONTHS * 4)
    candidates = [c for c in curve if c.weeks_to_clear <= target_weeks]
    if candidates:
        return max(candidates, key=lambda c: c.recoverable_revenue_eur)
    return min(curve, key=lambda c: c.weeks_to_clear)


# ── Live calls ─────────────────────────────────────────────────────


def _score_sku(
    client: AitoClient,
    sku: str,
    inv: dict,
    product: dict,
    recent_sales: list[dict],
) -> MarkdownRow | None:
    """Build the full markdown curve for one SKU and pick the
    proposed discount. Runs all five `_estimate` probes in parallel."""
    list_price = float(product.get("price_eur", 0) or 0)
    unit_cost = float(inv.get("unit_cost_eur", 0) or 0)
    current_stock = int(inv.get("current_stock", 0) or 0)
    reorder_point = int(inv.get("reorder_point", 1) or 1)
    if list_price <= 0:
        return None

    # Excess stock = what we want to clear (anything above 2× reorder).
    excess_units = max(0, current_stock - reorder_point * 2)
    tied_capital = excess_units * unit_cost
    if excess_units <= 0:
        return None

    recent = max(recent_sales, key=lambda r: r["month"]) if recent_sales else {}
    # Use the next month as the forecast anchor — same convention as
    # Inventory and Demand views.
    forecast_month = "2026-05"

    def probe(pct: int) -> MarkdownCurvePoint:
        price, units = _estimate_at_price(
            client, sku, list_price, pct, recent, forecast_month,
        )
        # Aito's `_estimate` returns null when K-NN finds no neighbor
        # for the (sku, price) combo — common at deeper discounts
        # where the SKU never sold below this price. Fall back to
        # the SKU's mean monthly units so the row is still useful.
        if units == 0.0:
            units = _avg_monthly_units(recent_sales)
        weekly_units = units / 4.33   # ~weeks per month
        weeks_to_clear = (
            excess_units / weekly_units if weekly_units > 0 else 999.0
        )
        # Cap "cleared" units at excess — past the horizon we'd be
        # eating into the next replenishment cycle, not really
        # "clearing" overstock anymore.
        horizon_weeks = CLEAR_HORIZON_MONTHS * 4.33
        cleared = min(excess_units, weekly_units * horizon_weeks)
        margin_per_unit = price - unit_cost
        recoverable_revenue = max(0.0, margin_per_unit * cleared)
        return MarkdownCurvePoint(
            discount_pct=pct,
            price_eur=price,
            monthly_units=round(units, 2),
            weeks_to_clear=round(weeks_to_clear, 1),
            margin_per_unit_eur=round(margin_per_unit, 2),
            recoverable_revenue_eur=round(recoverable_revenue, 2),
        )

    # Sequential within-SKU so the outer ThreadPoolExecutor controls
    # total in-flight Aito calls. 5 markdown probes × 4 SKUs in
    # parallel = 20 in-flight risked 429 spikes; 5 × 4 sequential
    # gives ~4 in-flight (one per outer worker).
    curve = sorted([probe(pct) for pct in MARKDOWN_LEVELS_PCT],
                   key=lambda c: c.discount_pct)

    best = _pick_best_markdown(curve)
    margin_lost = round(
        (list_price - best.price_eur) * min(
            excess_units,
            (best.monthly_units / 4.33) * CLEAR_HORIZON_MONTHS * 4.33,
        ),
        2,
    )

    return MarkdownRow(
        sku=sku,
        name=product.get("name", sku),
        pet_type=product.get("pet_type", ""),
        category=product.get("category", ""),
        current_stock=current_stock,
        reorder_point=reorder_point,
        list_price_eur=round(list_price, 2),
        unit_cost_eur=round(unit_cost, 2),
        excess_units=excess_units,
        tied_capital_eur=round(tied_capital, 2),
        proposed_discount_pct=best.discount_pct,
        proposed_price_eur=best.price_eur,
        proposed_weeks_to_clear=best.weeks_to_clear,
        proposed_recoverable_revenue_eur=best.recoverable_revenue_eur,
        proposed_margin_lost_eur=margin_lost,
        curve=list(curve),
    )


# ── Public entry point ─────────────────────────────────────────────


def get_markdowns(client: AitoClient) -> MarkdownResponse:
    """Survey the catalog for overstock SKUs and propose a markdown
    level for each.

    Reuses Inventory's fetchers (page through `inventory` /
    `products` / `monthly_sales`) so we don't duplicate the
    pagination logic. The expensive step is the per-SKU
    `_estimate` sweep — runs at most `MARKDOWN_TOP_N × len(MARKDOWN_LEVELS_PCT)`
    calls, parallelised per SKU and again across SKUs.
    """
    cached = cache.get("markdown:summary")
    if cached:
        return _from_dict(cached)

    started = time.perf_counter()

    # Lazy-import the inventory fetchers so we don't hand out a
    # public re-export of internal helpers.
    from src.inventory_service import (
        _fetch_all_inventory, _fetch_products, _fetch_recent_sales,
    )

    inv_rows = _fetch_all_inventory(client)
    products = _fetch_products(client)
    sales = _fetch_recent_sales(client)

    # Filter to overstock, sort by tied capital so the top-N is the
    # most cash-impact rows.
    overstock = []
    for r in inv_rows:
        if not _is_overstock(int(r["current_stock"]), int(r["reorder_point"])):
            continue
        prod = products.get(r["sku"], {})
        excess = max(0, int(r["current_stock"]) - int(r["reorder_point"]) * 2)
        tied = excess * float(r["unit_cost_eur"])
        overstock.append((tied, r, prod))
    overstock.sort(key=lambda t: -t[0])
    overstock = overstock[:MARKDOWN_TOP_N]

    def score(t: tuple[float, dict, dict]) -> MarkdownRow | None:
        _tied, inv, prod = t
        return _score_sku(client, inv["sku"], inv, prod,
                          sales.get(inv["sku"], []))

    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = [r for r in pool.map(score, overstock) if r is not None]

    rows.sort(key=lambda r: -r.proposed_recoverable_revenue_eur)

    # KPI roll-up across the proposed markdown set.
    # Capital freed = cost × cleared units (cash flowing back from
    # inventory into the bank). The contrast with `tied_capital`
    # tells the merchandiser how much of the stuck capital they
    # rescue with the proposed markdowns.
    total_tied = round(sum(r.tied_capital_eur for r in rows), 2)
    total_margin_earned = round(
        sum(r.proposed_recoverable_revenue_eur for r in rows), 2,
    )
    cleared_units_per_row: list[tuple[float, float]] = [
        (
            min(r.excess_units,
                (r.curve[next(i for i, c in enumerate(r.curve)
                              if c.discount_pct == r.proposed_discount_pct)]
                 .monthly_units / 4.33) * CLEAR_HORIZON_MONTHS * 4.33),
            r.unit_cost_eur,
        )
        for r in rows
    ]
    total_capital_freed = round(
        sum(u * c for u, c in cleared_units_per_row), 2,
    )
    total_excess_units = sum(r.excess_units for r in rows)

    kpis = [
        Kpi("Overstock targeted", float(len(rows)),
            f"{total_excess_units} excess units"),
        Kpi("Tied capital", total_tied, "stuck in excess inventory today"),
        Kpi("Capital freed", total_capital_freed,
            "cost basis of units cleared by proposed markdowns"),
        Kpi("Margin earned", total_margin_earned,
            "(price − cost) × cleared units at proposed markdowns"),
    ]

    elapsed = int((time.perf_counter() - started) * 1000)
    response = MarkdownResponse(
        kpis=kpis,
        proposals=rows,
        last_query={
            "endpoint": "_estimate",
            "body": {
                "from":     "monthly_sales",
                "where":    {
                    "product_sku": "<each overstock SKU>",
                    "month":       "2026-05",
                    "price_eur":   "<discounted price>",
                },
                "estimate": "units_sold",
            },
        },
        last_response_ms=elapsed,
    )
    cache.set("markdown:summary", response.to_dict(), ttl=1800)
    return response


def _from_dict(d: dict) -> MarkdownResponse:
    return MarkdownResponse(
        kpis=[Kpi(**k) for k in d["kpis"]],
        proposals=[
            MarkdownRow(
                **{k: v for k, v in row.items() if k != "curve"},
                curve=[MarkdownCurvePoint(**c) for c in row["curve"]],
            )
            for row in d["proposals"]
        ],
        last_query=d["last_query"],
        last_response_ms=d["last_response_ms"],
    )
