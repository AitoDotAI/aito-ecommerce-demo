"""Does a recent window say more about what a segment buys next than all earlier months? (ADR 0060, step 1.)

    uv run python scripts/period_backtest.py

For every single-trait segment of at least MIN_CUSTOMERS customers and every origin month, the shares of units by category (and by brand) over
the WINDOW months before the origin are set against the shares over all months before it, and each is scored against what the segment
bought in the FOLLOWING months. Distance is total variation (half the sum of absolute differences between the two share tables; 0 is
identical). Training only on months before the origin: nothing from the future leaks into the prediction. Offline: reads the fixtures.
"""
from __future__ import annotations

import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
MIN_CUSTOMERS = 100
WINDOW = 3
AHEAD = 3


def months_between(first: str, count: int) -> list[str]:
    year, month = map(int, first.split("-"))
    out = []
    for i in range(count):
        out.append(f"{year + (month - 1 + i) // 12}-{(month - 1 + i) % 12 + 1:02d}")
    return out


def shares(units: Counter) -> dict[str, float]:
    total = sum(units.values())
    return {k: v / total for k, v in units.items()} if total else {}


def distance(a: dict[str, float], b: dict[str, float]) -> float:
    return 0.5 * sum(abs(a.get(k, 0.0) - b.get(k, 0.0)) for k in set(a) | set(b))


def main() -> None:
    customers = {c["customer_id"]: c for c in json.loads((DATA / "customers.json").read_text())}
    products = {p["sku"]: p for p in json.loads((DATA / "products.json").read_text())}
    orders = {o["order_id"]: o for o in json.loads((DATA / "orders.json").read_text())}
    lines = json.loads((DATA / "order_lines.json").read_text())
    months = sorted({o["month"] for o in orders.values()})
    all_months = months_between(months[0], len(months))
    assert all_months == months, f"the data has a gap in its months: {months}"

    segments: dict[str, set[str]] = defaultdict(set)
    for c in customers.values():
        for trait in ("region", "pets", "first_source"):
            # A column with no value is left out of the row; those customers are in no segment of that trait.
            for value in str(c.get(trait, "")).split():
                segments[f"{trait}:{value}"].add(c["customer_id"])
    segments = {k: v for k, v in segments.items() if len(v) >= MIN_CUSTOMERS}

    # units[(segment, month)][field] -> Counter of category / brand units
    units: dict[tuple[str, str], dict[str, Counter]] = defaultdict(lambda: {"category": Counter(), "brand": Counter()})
    for line in lines:
        if line["returned"]:
            continue
        order = orders[line["order_id"]]
        product = products[line["product_sku"]]
        for name, members in segments.items():
            if order["customer_id"] in members:
                units[(name, order["month"])]["category"][product["category"]] += line["qty"]
                units[(name, order["month"])]["brand"][product["brand"]] += line["qty"]

    def pooled(name: str, field: str, span: list[str]) -> Counter:
        total: Counter = Counter()
        for m in span:
            total.update(units[(name, m)][field])
        return total

    for field in ("category", "brand"):
        gaps = []
        for name in segments:
            for i in range(WINDOW + 3, len(months) - AHEAD + 1):
                window, history, ahead = months[i - WINDOW:i], months[:i], months[i:i + AHEAD]
                actual = shares(pooled(name, field, ahead))
                from_window, from_history = shares(pooled(name, field, window)), shares(pooled(name, field, history))
                if not actual or not from_window or not from_history:
                    continue
                gaps.append(distance(from_window, actual) - distance(from_history, actual))
        n = len(gaps)
        mean = sum(gaps) / n
        se = math.sqrt(sum((g - mean) ** 2 for g in gaps) / (n - 1) / n)
        wins = sum(g < 0 for g in gaps) / n
        print(f"{field:9} {len(segments)} segments, {n} segment-origins: window minus all history, distance {mean:+.4f} ± {1.96 * se:.4f} "
              f"(negative = the window predicts the next {AHEAD} months better); the window is closer in {wins:.0%}")


if __name__ == "__main__":
    sys.exit(main())
