"""The metrics of ADR 0045's checks: an offer sells twice, per showing and by placement.

Read from one generated data dir; `scripts/planted_effects.py` judges them
(docs/verification/actionable-states-prereg.md, ADR 0045 addendum).
"""
from __future__ import annotations

from collections import defaultdict

from scripts.planted_effect_metrics import Fixtures

POSITIONS = range(10)


def _mean(values: list[float]) -> float:
    assert values, "nothing to average"
    return sum(values) / len(values)


def units_at_deep_offers(fx: Fixtures) -> float:
    """O2: mean units per state-month at a 20 %+ offer."""
    return _mean([ms["units_sold"] for ms in fx.load("monthly_sales") if ms["discount_band"] == "20+"])


def showings_on_offer(fx: Fixtures) -> float:
    """O3a: mean recorded showings per state-month on offer."""
    state = fx.state()
    return _mean([ms["showings"] for ms in fx.load("monthly_sales") if state[ms["product_state"]]["on_offer"]])


def click_rate_rises_by_position(fx: Fixtures) -> float:
    """O3b: how many of slots 1–9 of customers' lists are clicked at least as
    often as the slot above them (0 when clicks fall at every slot)."""
    clicks = defaultdict(lambda: [0, 0])
    for r in fx.impressions():
        if r["position"] in POSITIONS:
            clicks[r["position"]][0] += r["clicked"]
            clicks[r["position"]][1] += 1
    rate = [clicks[p][0] / clicks[p][1] for p in POSITIONS]
    return float(sum(later >= earlier for earlier, later in zip(rate, rate[1:])))
