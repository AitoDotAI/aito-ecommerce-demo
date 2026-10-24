"""What the shop decides or lives with each month: labels and stock (ADR 0038).

- **Labels.** The shop gives `recommended` and `staff_pick` to 5 % of the
  products on sale each, chosen at random every month, so their effect is
  identifiable (a natural experiment). `popular` is a visible rule: the top
  5 % of last month's units in each category.
- **Stock.** A monthly order-up-to plan per product (`StockBook`). A month
  is `low` when its opening stock won't last it and two more weeks: a late
  delivery, or last month's spike. It is decided at the month's start
  (ADR 0045), since the month's own sales follow from it.
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
LATE_DELIVERY_P = 0.15         # ADR 0045: the low share stays near 10 % with a causal state
LOW_STOCK_DAYS = 14
FORECAST_MONTHS = 3


def labels_for_month(seed: int, month: str, skus: list[str], last_month_units: dict[str, int] | None,
                     category_of: dict[str, str]) -> dict[str, str]:
    """sku → its label this month; products without one are left out.

    `last_month_units` is None in the first month: nothing has sold yet, so
    nothing is popular."""
    skus = sorted(skus)
    labels: dict[str, str] = {}
    rng = stream(seed, "labels", month)
    n = round(RANDOM_LABEL_SHARE * len(skus))
    chosen = rng.sample(skus, 2 * n)
    for sku in chosen[:n]:
        labels[sku] = "recommended"
    for sku in chosen[n:]:
        labels[sku] = "staff_pick"
    if last_month_units is None:
        return labels
    by_category: dict[str, list[str]] = defaultdict(list)
    for sku in skus:
        by_category[category_of[sku]].append(sku)
    for members in by_category.values():
        ranked = sorted(members, key=lambda s: (-last_month_units.get(s, 0), s))
        for sku in ranked[:max(1, round(POPULAR_SHARE * len(members)))]:
            if last_month_units.get(sku, 0) > 0:
                labels.setdefault(sku, "popular")    # a random label wins
    return labels


class StockBook:
    """Each product's stock, month by month: an order-up-to plan.

    At a month's start a delivery fills to `STOCK_COVER_MONTHS` of forecast
    demand, unless it is late. The month is `low` when that opening stock
    won't last the month and two more weeks: something a shop knows before
    its customers arrive. After the month, its units leave the shelf."""

    def __init__(self, seed: int):
        self.seed = seed
        self.history: dict[str, list[int]] = defaultdict(list)
        self.stock: dict[str, float] = {}

    def _forecast(self, sku: str) -> float | None:
        recent = self.history[sku][-FORECAST_MONTHS:]
        return sum(recent) / len(recent) if recent else None

    def opens_low(self, sku: str, month: str) -> bool:
        forecast = self._forecast(sku)
        if forecast is None or forecast == 0:
            # A launch is stocked to its plan; nothing sells, nothing runs low.
            self.stock.setdefault(sku, 0.0)
            return False
        late = stream(self.seed, "stock", sku, month).random() < LATE_DELIVERY_P
        if not late:
            self.stock[sku] = max(self.stock.get(sku, 0.0), forecast * STOCK_COVER_MONTHS)
        return self.stock[sku] < forecast * (1 + LOW_STOCK_DAYS / 30)

    def close_month(self, sku: str, units: int) -> None:
        self.stock[sku] = max(0.0, self.stock.get(sku, 0.0) - units)
        self.history[sku].append(units)


def review_count_band(n: int) -> str:
    if n == 0:
        return "none"
    if n <= 4:
        return "1-4"
    return "5-19" if n <= 19 else "20+"
