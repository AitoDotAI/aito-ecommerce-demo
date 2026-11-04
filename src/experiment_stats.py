"""The arithmetic behind the Experiments page (ADR 0064): profit per showing, the difference between two arms with its interval, and a policy's gain."""

from __future__ import annotations

import math
import random
import statistics

Z = 1.96            # 95 %
MIN_GAIN = 3.0      # percent: a per-person choice must beat the plain winner by this much (docs/verification/experiments-prereg.md)
BOOTSTRAP_ROUNDS = 400


def arm_figures(shown: int, bought: int, margin_eur: float) -> dict:
    rate = bought / shown if shown else 0.0
    return {"showings": shown, "purchases": bought, "rate": rate, "profit_per_showing": rate * margin_eur}


def profit_difference(first: tuple[int, int], second: tuple[int, int], first_margin: float, second_margin: float) -> dict:
    """The second arm's profit per showing less the first's, with a 95 % interval (normal approximation of two binomials).
    An arm is `(showings, purchases)`; a margin is what one sale earns on that arm."""
    def figures(shown: int, bought: int, margin: float) -> tuple[float, float]:
        rate = bought / shown
        return rate * margin, margin ** 2 * rate * (1 - rate) / shown
    (a, var_a), (b, var_b) = figures(*first, first_margin), figures(*second, second_margin)
    delta, spread = b - a, Z * math.sqrt(var_a + var_b)
    return {"delta": delta, "interval": [delta - spread, delta + spread]}


def verdict(difference: dict) -> str:
    low, high = difference["interval"]
    return "second arm better" if low > 0 else "control better" if high < 0 else "no clear difference"


def bootstrap_gain(per_customer: dict[str, list[tuple[float, float]]], rng: random.Random) -> dict:
    """Mean of (baseline value, policy value) pairs per customer, and the policy's gain over the baseline in percent with a 95 % interval over customers."""
    customers = list(per_customer.values())

    def gain(sample: list[list[tuple[float, float]]]) -> float:
        baseline = statistics.fmean(v for rows in sample for v, _ in rows)
        return 100 * (statistics.fmean(v for rows in sample for _, v in rows) - baseline) / baseline

    draws = sorted(gain([customers[rng.randrange(len(customers))] for _ in customers]) for _ in range(BOOTSTRAP_ROUNDS))
    lower, upper = draws[round(0.025 * BOOTSTRAP_ROUNDS)], draws[round(0.975 * BOOTSTRAP_ROUNDS) - 1]
    return {"gain_percent": gain(customers), "interval_percent": [lower, upper]}


def personal_choice_verdict(result: dict) -> str:
    """`choose per person` where the gain over the plain winner is at least `MIN_GAIN` percent and its interval is above zero; `small gain` where the
    interval is above zero but the gain is under that (real, but not worth a second way of choosing yet); otherwise `keep the plain winner`."""
    if result["interval_percent"][0] <= 0:
        return "keep the plain winner"
    return "choose per person" if result["gain_percent"] >= MIN_GAIN else "small gain"
