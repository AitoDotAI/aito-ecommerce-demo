"""When is a price finding real? The two rules the Price view applies.

Both exist because the view once presented noise as findings (demo
review, 2026-09-28): it opened on an "outlier" whose band came from two
sales, and ranked category "sweet spots" by lift alone, so the rarest
categories, whose lifts swing furthest by chance, came first.
"""

from __future__ import annotations

import math

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
                  f: float, n: float) -> tuple[float, float]:
    """95 % interval for a `_relate` lift, from the counts Aito returns in `fs`.

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
    return math.exp(log_lift - _Z95 * se), math.exp(log_lift + _Z95 * se)


def is_real_lift(lift: float, fs: dict) -> bool:
    """Enough support, and an interval that stays on one side of 1."""
    support = fs["fOnCondition"]
    if support < MIN_SWEET_SPOT_SUPPORT:
        return False
    low, high = lift_interval(lift, support, fs["fCondition"], fs["f"], fs["n"])
    return low > 1 or high < 1
