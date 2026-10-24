"""When is a price finding real? The rules the Price and Supply views apply.

Both exist because the view once presented noise as findings (demo
review, 2026-09-28): it opened on an "outlier" whose band came from two
sales, and ranked category "sweet spots" by lift alone, so the rarest
categories, whose lifts swing furthest by chance, came first.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# A band of mean ± 1.5σ from fewer observations is not a band: with two
# sales the σ is near zero and almost any list price falls outside it.
MIN_OUTLIER_OBSERVATIONS = 6

# A sweet spot needs this many rows in its category-and-band cell, and a
# 95 % interval on its lift that excludes 1.
MIN_SWEET_SPOT_SUPPORT = 30
_Z95 = 1.96


def is_price_outlier(list_price: float, mean: float, std: float, observations: int) -> bool:
    """List price outside mean ± 1.5σ of the SKU's realised prices, judged
    only when there are enough observations for the band to mean anything."""
    if observations < MIN_OUTLIER_OBSERVATIONS:
        return False
    return not (mean - 1.5 * std <= list_price <= mean + 1.5 * std)


def lift_interval(lift: float, f_on_condition: float, f_condition: float,
                  f: float, n: float, z: float = _Z95) -> tuple[float, float]:
    """95 % interval for a `_relate` lift, from the counts Aito returns in `fs`.
    A larger `z` gives a wider interval (Shop analytics passes a Bonferroni z).

    Lift is P(category | band) / P(category), a ratio of two proportions.
    The width uses the relative-risk standard error for two independent
    groups. Here the reference group (everyone) contains the band, so the
    two proportions are positively correlated and the true interval is
    narrower: this one is conservative, which is the safe side for "is
    it real". The centre is Aito's own lift (which may be prior-smoothed);
    only the width comes from the raw counts.
    """
    if f_on_condition <= 0:
        return 0.0, math.inf
    se = math.sqrt(max(1 / f_on_condition - 1 / f_condition + 1 / f - 1 / n, 0.0))
    log_lift = math.log(lift)
    return math.exp(log_lift - z * se), math.exp(log_lift + z * se)


def is_real_lift(lift: float, fs: dict) -> bool:
    """Enough support, and an interval that stays on one side of 1."""
    support = fs["fOnCondition"]
    if support < MIN_SWEET_SPOT_SUPPORT:
        return False
    low, high = lift_interval(lift, support, fs["fCondition"], fs["f"], fs["n"])
    return low > 1 or high < 1


@dataclass(frozen=True)
class PriceBand:
    """A SKU's list price against the prices it actually sold at."""
    list_price_eur: float
    mean_price_eur: float
    band_low_eur: float              # mean − 1.5σ, floored at 0
    band_high_eur: float             # mean + 1.5σ
    observations: int
    outlier: bool                    # list price outside the band (`is_price_outlier`)


def price_band(realised_prices: list[float], list_price: float) -> PriceBand:
    """The fair band of one SKU from its realised prices (`product_states`)."""
    assert realised_prices, f"no realised prices to band a list price of {list_price}"
    mean = sum(realised_prices) / len(realised_prices)
    std = math.sqrt(sum((p - mean) ** 2 for p in realised_prices) / len(realised_prices))
    return PriceBand(
        list_price_eur=round(list_price, 2),
        mean_price_eur=round(mean, 2),
        band_low_eur=round(max(0.0, mean - 1.5 * std), 2),
        band_high_eur=round(mean + 1.5 * std, 2),
        observations=len(realised_prices),
        outlier=is_price_outlier(list_price, mean, std, len(realised_prices)),
    )
