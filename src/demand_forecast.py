"""Next month's units for one SKU — the forecast Demand and Inventory share.

`_estimate`, not `_predict`: the question is the expected number of
units, not the single most probable integer (see ADR 0014).

The evidence is last month's units plus the product profile. The
forecast month itself is NOT evidence: no training row has it, so
conditioning on it made the estimate fall back to the SKU's all-time
average, far below the current level of a growing SKU.
"""

from __future__ import annotations

from src.aito_client import AitoClient
from src.why_processor import process_estimate_why

FORECAST_MONTH = "2026-05"   # the month we predict for
LATEST_MONTH = "2026-04"     # the last month with sales: the held-out test month

SEASON_BY_MONTH = {
    1: "winter", 2: "winter", 3: "spring", 4: "spring",
    5: "spring", 6: "summer", 7: "summer", 8: "summer",
    9: "autumn", 10: "autumn", 11: "autumn", 12: "winter",
}


def last_month_units(sales_rows: list[dict]) -> int:
    """Units sold in LATEST_MONTH; 0 when the SKU sold nothing then.
    Rows exist only for months with sales, so a missing row means 0."""
    latest = [r for r in sales_rows if r["month"] == LATEST_MONTH]
    assert len(latest) <= 1, f"{len(latest)} rows for one SKU in {LATEST_MONTH}"
    return int(latest[0]["units_sold"]) if latest else 0


def forecast_where(sku: str, profile: dict, units_last_month: int) -> dict:
    return {
        "product_sku":      sku,
        "units_last_month": units_last_month,
        "pet_type":         profile["pet_type"],
        "category":         profile["category"],
        "brand":            profile["brand"],
        "season":           SEASON_BY_MONTH[int(FORECAST_MONTH.split("-")[1])],
    }


def forecast_units(client: AitoClient, sku: str, sales_rows: list[dict]) -> tuple[int, dict | None]:
    """Expected units for FORECAST_MONTH (rounded) and the popover-shaped
    why payload. `sales_rows` is the SKU's monthly_sales history."""
    assert sales_rows, f"no sales history for {sku}"
    profile = max(sales_rows, key=lambda r: r["month"])
    where = forecast_where(sku, profile, last_month_units(sales_rows))
    res = client.estimate("monthly_sales", where=where, estimate_field="units_sold")
    estimate = res.get("estimate")
    assert estimate is not None, f"_estimate returned no estimate for {sku}: {res}"
    why = process_estimate_why(res.get("why"), float(estimate), field_label="units_sold")
    return max(0, int(round(float(estimate)))), why
