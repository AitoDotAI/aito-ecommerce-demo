"""Does anything beat 'next month sells like the last three' when demand moves over time? (ADR 0062)

    uv run python scripts/harder_demand_backtest.py [DATA_DIR ...]

For each of the last seven months, an adjustment is fitted ONLY on the months before it and scored by mean absolute error in units over every
product-month, against the plain three-month rate, with the interval of the paired difference. The adjustments use what a shop can see:
the category and season; the momentum (last month against the three-month rate); the product's age; the product's own sales a year ago.
Offline: reads monthly_sales.json and product_states.json of each directory (default: the committed fixtures).
"""
from __future__ import annotations

import functools
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

TEST_MONTHS = 7
SEASON = {"12": "winter", "01": "winter", "02": "winter", "03": "spring", "04": "spring", "05": "spring", "06": "summer", "07": "summer", "08": "summer",
          "09": "autumn", "10": "autumn", "11": "autumn"}


def momentum(last: float, rate: float) -> str:
    return "none" if rate == 0 else "up" if last > 1.3 * rate else "down" if last < 0.7 * rate else "flat"


def main(directories: list[Path]) -> None:
    for directory in directories:
        sales = json.loads((directory / "monthly_sales.json").read_text())
        states = {(p["product_sku"], p["month"]): p for p in json.loads((directory / "product_states.json").read_text())}
        units: dict[str, dict[str, int]] = defaultdict(dict)
        category, signals = {}, {}
        for r in sales:
            signals[(r["product_sku"], r["month"])] = (r.get("in_season"), r.get("trend"), r.get("months_on_sale"), r.get("price_vs_category"))
            units[r["product_sku"]][r["month"]] = r["units_sold"]
            category[r["product_sku"]] = r["category"]
        months = sorted({r["month"] for r in sales})

        @functools.cache
        def rows(i: int) -> list[dict]:
            out = []
            for sku, by_month in units.items():
                state = states.get((sku, months[i]))
                if months[i] not in by_month or not state:
                    continue
                last = by_month.get(months[i - 1], 0)
                rate = sum(by_month.get(months[i - k], 0) for k in (1, 2, 3)) / 3
                year_ago = by_month.get(months[i - 12]) if i >= 12 else None
                recent = [by_month.get(months[i - k], 0) for k in range(6, 0, -1)]
                slope = (sum((k - 2.5) * v for k, v in enumerate(recent)) / 17.5) if i >= 6 else 0.0
                out.append({"sku": sku, "signals": signals.get((sku, months[i])), "rate": rate, "trend": max(0.0, sum(recent[-3:]) / 3 + 2 * slope), "growth": max(0.0, last + slope), "actual": by_month[months[i]], "category": category[sku], "season": SEASON[months[i][-2:]],
                            "age": state["age"], "stars": state["rating_band"], "momentum": momentum(last, rate), "year_ago": year_ago, "last": last})
            return out

        keys = {
            "category, season": lambda r: (r["category"], r["season"]),
            "momentum": lambda r: r["momentum"],
            "age, stars": lambda r: (r["age"], r["stars"]),
            "all of them": lambda r: (r["category"], r["season"], r["momentum"], r["age"]),
        }

        def fit(until: int, key, member=lambda r: True) -> dict:
            sold, rate = defaultdict(float), defaultdict(float)
            for i in range(3, until):
                for r in filter(member, rows(i)):
                    sold[key(r)] += r["actual"]
                    rate[key(r)] += r["rate"]
            return {k: sold[k] / rate[k] for k in rate if rate[k] > 0}

        print(f"\n{directory}")
        for name, key in keys.items():
            factors = {i: fit(i, key) for i in range(len(months) - TEST_MONTHS, len(months))}
            report(name, [abs(r["actual"] - r["rate"] * factors[i].get(key(r), 1.0)) - abs(r["actual"] - r["rate"])
                          for i in factors for r in rows(i)])
        if sales[0].get("in_season") is not None:
            slice_report(directory, sales, months, rows, fit)
        # Where the drivers should matter most: the products that are new.
        key = keys["age, stars"]
        factors = {i: fit(i, key) for i in range(len(months) - TEST_MONTHS, len(months))}
        report("age, stars, new products only", [abs(r["actual"] - r["rate"] * factors[i].get(key(r), 1.0)) - abs(r["actual"] - r["rate"])
                                                 for i in factors for r in rows(i) if r["age"] == "new"])
        # Per-product forecasters: the straight line through the last six months, carried two months on from their middle; the last month plus the slope.
        for name, field in (("six-month trend line", "trend"), ("last month plus slope", "growth")):
            for label, big in (("all products", 0.0), ("products selling 10+ a month", 10.0)):
                report(f"{name}, {label}", [abs(r["actual"] - r[field]) - abs(r["actual"] - r["rate"])
                                            for i in range(len(months) - TEST_MONTHS, len(months)) for r in rows(i) if r["rate"] >= big])
        # The same month a year ago, for the products that have one: seasonal ware repeats; a trend does not.
        report("same month last year", [abs(r["actual"] - r["year_ago"]) - abs(r["actual"] - r["rate"])
                                        for i in range(len(months) - TEST_MONTHS, len(months)) for r in rows(i) if r["year_ago"] is not None])


def report(name: str, gaps: list[float]) -> None:
    n = len(gaps)
    mean = sum(gaps) / n
    half = 1.96 * math.sqrt(sum((g - mean) ** 2 for g in gaps) / (n - 1) / n)
    verdict = "better" if mean + half < 0 else "worse" if mean - half > 0 else "no clear difference"
    print(f"  {name:46} minus the plain three-month rate, mean absolute error in units: {mean:+.3f} ± {half:.3f} over {n} product-months ({verdict})")



def slice_report(directory: Path, sales: list, months: list, rows, fit) -> None:
    """The slices of the harder dataset, each with the columns a shop would have for it, scored by error in units against the plain rate."""
    from scripts.harder_demand_evaluate import slices
    named = slices(directory)
    sliced = {
        "seasonal ware": (lambda r: r["sku"] in named["seasonal ware"], {"in season": lambda r: r["signals"][0]}),
        "trending products": (lambda r: r["sku"] in named["trending products"], {"trend": lambda r: r["signals"][1]}),
        "launches": (lambda r: r["sku"] in named["launches"], {"months on sale": lambda r: r["signals"][2],
                                                               "months on sale, price": lambda r: r["signals"][2:]}),
    }
    for name, (member, adjustments) in sliced.items():
        for label, key in adjustments.items():
            factors = {i: fit(i, key, member) for i in range(len(months) - TEST_MONTHS, len(months))}
            gap = lambda r, f: abs(r["actual"] - r["rate"] * f.get(key(r), 1.0)) - abs(r["actual"] - r["rate"])
            report(f"{name}: by {label}", [gap(r, factors[i]) for i in factors for r in rows(i) if member(r)])
            # Guarded: the adjustment is used for a month only if, fitted on the months before the last of the months it was fitted on,
            # it beat the plain rate on that last month. Otherwise the plain rate stands. Still only earlier months are looked at.
            guarded = []
            for i in factors:
                trial = fit(i - 1, key, member)
                held_out = [gap(r, trial) for r in rows(i - 1) if member(r)]
                use = held_out and sum(held_out) < 0
                guarded += [gap(r, factors[i]) if use else 0.0 for r in rows(i) if member(r)]
            report(f"{name}: by {label}, guarded", guarded)


if __name__ == "__main__":
    main([Path(a) for a in sys.argv[1:]] or [Path(__file__).resolve().parent.parent / "data"])
