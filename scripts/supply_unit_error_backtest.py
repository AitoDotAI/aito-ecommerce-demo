"""Does a driver adjustment beat 'next month sells like the last three' on units, by absolute error? (ADR 0061, the gate for the reorder list.)

    uv run python scripts/supply_unit_error_backtest.py

For each of the last seven months, a factor per group (stars band; stars band and age; stars band and season) is fitted ONLY on the months before it:
the group's units sold divided by its units over the previous three months' rate. The adjusted prediction is the three-month rate times the factor. The
score is the mean absolute error in units over every product-month, against the plain three-month rate, with the interval of the paired difference.
Offline: reads the fixtures.
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
TEST_MONTHS = 7
SEASON = {"12": "winter", "01": "winter", "02": "winter", "03": "spring", "04": "spring", "05": "spring", "06": "summer", "07": "summer", "08": "summer",
          "09": "autumn", "10": "autumn", "11": "autumn"}


def main() -> None:
    sales = json.loads((DATA / "monthly_sales.json").read_text())
    states = {(p["product_sku"], p["month"]): p for p in json.loads((DATA / "product_states.json").read_text())}
    by_sku: dict[str, dict[str, int]] = defaultdict(dict)
    for r in sales:
        by_sku[r["product_sku"]][r["month"]] = r["units_sold"]
    months = sorted({r["month"] for r in sales})

    def rows(i: int) -> list[tuple]:
        out = []
        for sku, units in by_sku.items():
            state = states.get((sku, months[i]))
            if months[i] in units and state:
                rate = sum(units.get(months[i - k], 0) for k in (1, 2, 3)) / 3
                out.append((rate, units[months[i]], state["rating_band"], state["age"], SEASON[months[i][-2:]]))
        return out

    def fit(until: int, key) -> dict:
        sold, rate = defaultdict(float), defaultdict(float)
        for i in range(3, until):
            for r in rows(i):
                sold[key(r)] += r[1]
                rate[key(r)] += r[0]
        return {k: sold[k] / rate[k] for k in rate if rate[k] > 0}

    for name, key in (("stars band", lambda r: r[2]), ("stars band, age", lambda r: (r[2], r[3])), ("stars band, season", lambda r: (r[2], r[4]))):
        gaps = []
        for i in range(len(months) - TEST_MONTHS, len(months)):
            factor = fit(i, key)
            for r in rows(i):
                gaps.append(abs(r[1] - r[0] * factor.get(key(r), 1.0)) - abs(r[1] - r[0]))
        n = len(gaps)
        mean = sum(gaps) / n
        half = 1.96 * math.sqrt(sum((g - mean) ** 2 for g in gaps) / (n - 1) / n)
        print(f"{name:20} adjusted minus plain three-month rate, mean absolute error in units: {mean:+.3f} ± {half:.3f} over {n} product-months "
              f"({'better' if mean + half < 0 else 'worse' if mean - half > 0 else 'no clear difference'})")


if __name__ == "__main__":
    sys.exit(main())
