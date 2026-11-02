"""Demand that moves over time (ADR 0062): seasonal ware, trends, and launches that become hits or flops.

The older demand effects are flat: a category has a season, a launch gets a fixed bump for three months. Here a product
has a time profile of its own, each from an RNG stream of its own and behind its own switch (off in the committed
fixtures; `scripts/harder_demand_backtest.py` turns them on), so a null generation with one off moves no other draw.

  D1  Seasonal ware: 36 products sell mostly in one season (winter, summer, or the weeks before Christmas) and little outside it.
  D2  Trends: 36 products rise, or fade, month after month from a month of their own.
  D3  Launches: how far a new product takes off depends on its price against its category and on its quality (which the stars
      show once reviews arrive): a good, fairly priced launch ramps up for four months and settles above where it began; a poor or
      dear one is a flop.

Everything is fiction drawn from the seed; only the pick weight of a product in a month changes.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass

from data import planted_switches
from data.planted_switches import stream

SEASONAL_CATEGORIES = frozenset({"toys", "accessories", "treats", "grooming", "health"})
N_SEASONAL = 36
N_TRENDING = 36
# month number of the peak, and how sharply it falls away (months); in-season ×PEAK, out of season ×OFF.
SEASON_SHAPES = {"winter": (1, 3.0), "summer": (7, 3.0), "christmas": (12, 1.5)}
PEAK, OFF = 5.0, 0.35
TREND_RATE = 0.14            # per month: rising ×(1+r)^t up to ×4, fading ×(1-r)^t down to ×0.2
TREND_CAP, TREND_FLOOR = 4.0, 0.2
HIT_QUALITY = {"excellent": 1.8, "good": 1.2, "ok": 0.7, "poor": 0.25}
RAMP_MONTHS = 4
LAUNCH_MONTHS = 8            # how long a launch is shaped by D3, instead of the flat bump of ADR 0032


@dataclass(frozen=True)
class Dynamics:
    seasonal: dict[str, str]                 # sku → "winter" | "summer" | "christmas"
    trend: dict[str, tuple[int, int]]        # sku → (direction +1 / −1, index of the month it starts)
    launch_strength: dict[str, float]        # sku → how far its launch takes off (price × quality)
    months: tuple[str, ...]

    def factor(self, sku: str, month: str, launch_month: str | None) -> float:
        """The pick weight of `sku` in `month`, from the switches that are on."""
        weight = 1.0
        if planted_switches.ON["D1"] and sku in self.seasonal:
            weight *= _season_weight(self.seasonal[sku], int(month[5:]))
        if planted_switches.ON["D2"] and sku in self.trend:
            direction, start = self.trend[sku]
            steps = max(0, self.months.index(month) - start)
            weight *= min(TREND_CAP, (1 + TREND_RATE) ** steps) if direction > 0 else max(TREND_FLOOR, (1 - TREND_RATE) ** steps)
        return weight

    def launch_factor(self, sku: str, month: str, launch_month: str) -> float | None:
        """D3's pick weight for a new product (None when D3 is off or the launch is older than the shaped months)."""
        if not planted_switches.ON["D3"]:
            return None
        age = self.months.index(month) - self.months.index(launch_month)
        if age >= LAUNCH_MONTHS:
            return None
        strength = self.launch_strength[sku]
        ramp = min(1.0, (age + 1) / RAMP_MONTHS)
        return 1.0 + (2.0 * strength - 1.0) * ramp if strength >= 1 else 0.4 + (1.0 - 0.4) * strength


def _season_weight(season: str, month: int) -> float:
    peak, width = SEASON_SHAPES[season]
    distance = min(abs(month - peak), 12 - abs(month - peak))
    return OFF + (PEAK - OFF) * math.exp(-(distance / width) ** 2)


def plan(seed: int, products: list, months: list[str], launch_month: dict[str, str], anchors: frozenset[str]) -> Dynamics:
    """Choose the seasonal and trending products and each launch's strength. Anchors and launches keep their own stories."""
    free = sorted((p for p in products if p.sku not in anchors and p.sku not in launch_month), key=lambda p: p.sku)
    rng = stream(seed, "D1", "choose")
    seasonal_pool = [p for p in free if p.category in SEASONAL_CATEGORIES]
    seasonal = {p.sku: rng.choice(list(SEASON_SHAPES)) for p in rng.sample(seasonal_pool, N_SEASONAL)}
    rng = stream(seed, "D2", "choose")
    trend_pool = [p for p in free if p.sku not in seasonal and p.pet_type in ("dog", "cat")]
    trend = {p.sku: (rng.choice((1, -1)), rng.randrange(2, len(months) - 8)) for p in rng.sample(trend_pool, N_TRENDING)}
    # A launch's price against the median of its pet and category: dearer than that holds it back, cheaper lifts it.
    from data import review_chain
    medians: dict[tuple[str, str], float] = {}
    for key in {(p.pet_type, p.category) for p in products}:
        medians[key] = statistics.median(p.price_eur for p in products if (p.pet_type, p.category) == key)
    strength = {}
    for p in products:
        if p.sku in launch_month:
            price_ratio = min(1.6, max(0.6, medians[(p.pet_type, p.category)] / p.price_eur)) ** 1.5
            strength[p.sku] = HIT_QUALITY[review_chain.quality(p.sku)] * price_ratio
    return Dynamics(seasonal, trend, strength, tuple(months))
