"""What the shop decides or lives with each month: labels and stock (ADR 0038).

- **Labels.** The shop gives `recommended` and `staff_pick` to 5 % of the
  products on sale each, chosen at random every month, so their effect is
  identifiable (a natural experiment). `popular` is a visible rule: the top
  5 % of last month's units in each category.
- **Stock.** A monthly order-up-to plan per product. A month is `low` when
  its closing stock falls under two weeks of the forecast demand: a demand
  spike, or a late delivery.
- **Review count**, as a band (`none`, `1-4`, `5-19`, `20+`), from the
  reviews written before the month.

Each decision draws from its own seeded RNG (`data/planted_switches.py`).
"""

from __future__ import annotations

from collections import defaultdict

from data.planted_switches import stream

RANDOM_LABEL_SHARE = 0.05           # each of recommended, staff_pick
POPULAR_SHARE = 0.05
STOCK_COVER_MONTHS = 2.2            # a delivery fills to this much forecast demand
LATE_DELIVERY_P = 0.08
LOW_STOCK_DAYS = 14
FORECAST_MONTHS = 3


def plan_labels(seed: int, on_sale: dict[str, list[str]], units: dict[tuple[str, str], int],
                category_of: dict[str, str]) -> dict[tuple[str, str], str]:
    """(sku, month) → its label; products without one are left out.

    `on_sale` maps a month to the SKUs on sale in it; `units` holds each
    (sku, month)'s units sold."""
    labels: dict[tuple[str, str], str] = {}
    months = sorted(on_sale)
    for i, month in enumerate(months):
        skus = sorted(on_sale[month])
        rng = stream(seed, "labels", month)
        n = round(RANDOM_LABEL_SHARE * len(skus))
        chosen = rng.sample(skus, 2 * n)
        for sku in chosen[:n]:
            labels[(sku, month)] = "recommended"
        for sku in chosen[n:]:
            labels[(sku, month)] = "staff_pick"
        if i == 0:
            continue    # no last month to be popular in
        by_category: dict[str, list[str]] = defaultdict(list)
        for sku in skus:
            by_category[category_of[sku]].append(sku)
        for category, members in by_category.items():
            ranked = sorted(members, key=lambda s: (-units.get((s, months[i - 1]), 0), s))
            top = ranked[:max(1, round(POPULAR_SHARE * len(members)))]
            for sku in top:
                if units.get((sku, months[i - 1]), 0) > 0:
                    labels.setdefault((sku, month), "popular")    # a random label wins
    return labels


def plan_stock(seed: int, on_sale: dict[str, list[str]], units: dict[tuple[str, str], int]) -> set[tuple[str, str]]:
    """The (sku, month)s whose stock ran low: closing stock under two weeks of forecast demand."""
    months_of: dict[str, list[str]] = defaultdict(list)
    for month in sorted(on_sale):
        for sku in on_sale[month]:
            months_of[sku].append(month)
    low: set[tuple[str, str]] = set()
    for sku in sorted(months_of):
        rng = stream(seed, "stock", sku)
        history: list[int] = []
        stock: float | None = None
        for month in months_of[sku]:
            demand = units.get((sku, month), 0)
            # A launch is stocked to its own first month: there is no history yet.
            recent = history[-FORECAST_MONTHS:]
            forecast = sum(recent) / len(recent) if recent else float(demand)
            late = rng.random() < LATE_DELIVERY_P
            target = forecast * STOCK_COVER_MONTHS
            if stock is None:
                stock = target
            elif not late:
                stock = max(stock, target)
            closing = stock - demand
            if forecast > 0 and closing < forecast * LOW_STOCK_DAYS / 30:
                low.add((sku, month))
            stock = max(0.0, closing)
            history.append(demand)
    return low


def review_count_band(n: int) -> str:
    if n == 0:
        return "none"
    if n <= 4:
        return "1-4"
    return "5-19" if n <= 19 else "20+"
