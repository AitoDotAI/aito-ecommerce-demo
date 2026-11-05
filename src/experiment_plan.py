"""What-if controls for an experiment (ADR 0064, slice 3): what a split, an exploration floor and a guardrail would mean, projected from the arms' counted evidence.

Nothing is served or changed: the Shop does not show these arms, so a control cannot move real showings. The projection says what the same traffic
would earn under the chosen settings if the arms keep earning what they have earned, and how long a clear answer would take."""

from __future__ import annotations

import math

from src.experiment_stats import Z, profit_difference, verdict

LIMITS = {"allocation": (0.05, 0.95), "floor": (0.0, 0.5), "guardrail_percent": (1.0, 100.0)}
LONGEST_WAIT_MONTHS = 36


def _checked(name: str, value: float) -> float:
    low, high = LIMITS[name]
    if not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}, not {value}")
    return value


def _profit_per_showing(arm: dict) -> float:
    return arm["purchases"] / arm["showings"] * arm["margin_eur"]


def _variance_per_showing(arm: dict) -> float:
    rate = arm["purchases"] / arm["showings"]
    return arm["margin_eur"] ** 2 * rate * (1 - rate)


def plan(experiment: dict, months: int, allocation: float, floor: float, guardrail_percent: float) -> dict:
    """`allocation` is the share of showings on the second arm while testing; `floor` the share the worse arm keeps once a winner is decided;
    `guardrail_percent` how much less than the control the second arm may earn per showing, with the data clearly saying so, before it is stopped."""
    allocation, floor, guardrail_percent = _checked("allocation", allocation), _checked("floor", floor), _checked("guardrail_percent", guardrail_percent)
    control, second = experiment["arms"]
    if not (control["showings"] and second["showings"]):
        raise ValueError("The experiment has no showings yet, so there is nothing to project from")
    monthly = (control["showings"] + second["showings"]) / months
    p_control, p_second = _profit_per_showing(control), _profit_per_showing(second)
    better, worse = (second, control) if p_second >= p_control else (control, second)
    difference = profit_difference((control["showings"], control["purchases"]), (second["showings"], second["purchases"]), control["margin_eur"], second["margin_eur"])
    testing = monthly * ((1 - allocation) * p_control + allocation * p_second)
    decided = monthly * ((1 - floor) * _profit_per_showing(better) + floor * _profit_per_showing(worse))
    upper = difference["interval"][1]
    return {
        "monthly_showings": monthly,
        "testing": {"profit_per_month": testing},
        "decided": {"arm": better["arm"], "profit_per_month": decided},
        "all_control": {"profit_per_month": monthly * p_control},
        "cost_of_testing_per_month": decided - testing,
        "months_to_clear": _months_to_clear(control, second, difference, allocation, monthly),
        "guardrail": {"trips": upper < -guardrail_percent / 100 * p_control, "limit_eur": -guardrail_percent / 100 * p_control, "upper_end_eur": upper},
        "verdict_now": verdict(difference),
    }


def _months_to_clear(control: dict, second: dict, difference: dict, allocation: float, monthly: float) -> int | None:
    """Further months until the interval of the difference excludes zero at this split, if the difference stays as measured; `None` beyond three years."""
    if difference["interval"][0] > 0 or difference["interval"][1] < 0:
        return 0
    if difference["delta"] == 0:
        return None
    needed = Z ** 2 * (_variance_per_showing(control) / (1 - allocation) + _variance_per_showing(second) / allocation) / difference["delta"] ** 2
    extra = max(0.0, needed - control["showings"] - second["showings"]) / monthly
    return math.ceil(extra) if extra <= LONGEST_WAIT_MONTHS else None
