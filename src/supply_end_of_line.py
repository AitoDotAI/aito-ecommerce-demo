"""Lines to end (ADR 0061): the second lever on supply is demand.

Reordering and marking down adjust stock; a product that ties up capital and will not clear even at the deepest markdown the page tests is a
candidate to end: stop reordering it and sell the stock down. A product with its season ahead is held, not listed: it will move on its own.
The page recommends; the shop decides.
"""

from __future__ import annotations

# A product has a season ahead when, in the same three calendar months a year ago, it sold at least this many times its monthly average of the
# other months, and at least MIN_SEASON_UNITS in all. Both guards keep one lucky month from exempting a dead line.
SEASON_RATIO = 2.0
MIN_SEASON_UNITS = 6
AHEAD_MONTHS = 3
MIN_HISTORY_MONTHS = 13      # a year ago has to exist


def season_ahead(sales_rows: list[dict], planning_month: str) -> bool:
    """Did this product sell much more in the three months from `planning_month` a year ago than in its other months?"""
    if len(sales_rows) < MIN_HISTORY_MONTHS:
        return False
    year, month = map(int, planning_month.split("-"))
    window = {f"{year - 1 + (month - 1 + i) // 12}-{(month - 1 + i) % 12 + 1:02d}" for i in range(AHEAD_MONTHS)}
    inside = [int(r["units_sold"]) for r in sales_rows if r["month"] in window]
    outside = [int(r["units_sold"]) for r in sales_rows if r["month"] not in window]
    if len(inside) < AHEAD_MONTHS or not outside:
        return False
    return sum(inside) >= MIN_SEASON_UNITS and sum(inside) / len(inside) >= SEASON_RATIO * max(sum(outside) / len(outside), 0.1)


def end_of_line(rows: list, sales_by_sku: dict[str, list[dict]], planning_month: str) -> list[dict]:
    """The scored overstock rows that will not clear at the deepest markdown and have no season ahead, largest capital first."""
    out = [{"sku": r.sku, "name": r.name, "category": r.category, "current_stock": r.current_stock, "excess_units": r.excess_units,
            "tied_capital_eur": r.tied_capital_eur, "discount_pct": r.markdown.discount_pct, "weeks_to_clear": r.markdown.weeks_to_clear,
            "price_at_deepest_eur": r.markdown.price_eur, "unit_cost_eur": r.unit_cost_eur, "below_cost": r.markdown.price_eur < r.unit_cost_eur}
           for r in rows if r.markdown.action == "wont_clear" and not season_ahead(sales_by_sku[r.sku], planning_month)]
    return sorted(out, key=lambda c: -c["tied_capital_eur"])
