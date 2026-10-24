"""Supply's markdown action: the shallowest discount that clears the excess.

`choose` is the rule on a curve of Aito's estimates; `propose_markdown`
asks for that curve. A fake client stands in for Aito and answers each
`_estimate` from the price it is asked at.
"""

from __future__ import annotations

import pytest

from src.aito_client import AitoError
from src.demand_forecast import LATEST_MONTH
from src.markdown_proposal import (
    DISCOUNT_LEVELS_PCT, HORIZON_WEEKS, MarkdownPoint, choose, excess_units, propose_markdown,
)

LIST_PRICE, UNIT_COST = 10.0, 6.0


def curve(*monthly_units: float, excess: int) -> list[MarkdownPoint]:
    """A curve with these units at 0, 5, 10, 15 and 20 % off."""
    return [MarkdownPoint(pct, LIST_PRICE * (1 - pct / 100), units,
                          round(excess / (units / 4.33), 1) if units else None)
            for pct, units in zip(DISCOUNT_LEVELS_PCT, monthly_units)]


def test_excess_is_stock_above_twice_the_reorder_point():
    assert excess_units(current_stock=100, reorder_point=20) == 60
    assert excess_units(current_stock=30, reorder_point=20) == 0


def test_a_sku_that_sells_through_at_full_price_is_held_not_marked_down():
    # 40 a month clears 60 excess units in 6.5 weeks, inside the horizon.
    proposal = choose(curve(40, 42, 44, 46, 48, excess=60), 60, LIST_PRICE, UNIT_COST)

    assert proposal.action == "hold"
    assert proposal.discount_pct == 0
    assert proposal.margin_given_up_eur == 0
    assert proposal.capital_freed_eur == 60 * UNIT_COST


def test_the_shallowest_discount_that_clears_within_the_horizon_is_proposed():
    # 60 units need ~20 a month to clear in 13 weeks: 10 % off is the first to get there.
    proposal = choose(curve(15, 17, 21, 24, 27, excess=60), 60, LIST_PRICE, UNIT_COST)

    assert proposal.action == "markdown"
    assert proposal.discount_pct == 10
    assert proposal.weeks_to_clear <= HORIZON_WEEKS
    assert proposal.units_cleared == 60
    # At full price 15 a month sells 45 in the horizon, so the markdown adds 15.
    assert proposal.extra_units_vs_full_price == 15
    assert proposal.margin_given_up_eur == pytest.approx(1.0 * 60)


def test_when_no_discount_clears_it_the_row_says_so_instead_of_proposing_a_cut():
    """The old Markdown view proposed the deepest cut even when it cleared
    nothing, and lost margin on every row (demo review, 2026-09-28)."""
    proposal = choose(curve(2, 2.1, 2.2, 2.3, 2.4, excess=60), 60, LIST_PRICE, UNIT_COST)

    assert proposal.action == "wont_clear"
    assert proposal.discount_pct == 20     # the numbers shown are "even at 20 % off"
    assert proposal.weeks_to_clear > HORIZON_WEEKS


def test_an_estimate_of_zero_units_never_clears():
    proposal = choose(curve(0, 0, 0, 0, 0, excess=10), 10, LIST_PRICE, UNIT_COST)

    assert proposal.action == "wont_clear"
    assert proposal.weeks_to_clear is None
    assert proposal.units_cleared == 0


class PriceAito:
    """Answers `_estimate units_sold` with more units the lower the price."""

    def __init__(self, estimate_at=lambda price: 50 - 2 * price):
        self.estimate_at = estimate_at
        self.calls: list[dict] = []

    def estimate(self, table, where, estimate_field, model=None, with_why=True):
        self.calls.append({"table": table, "where": where, "field": estimate_field, "model": model})
        return {"estimate": self.estimate_at(where["price_eur"])}


PROFILE = {"pet_type": "cat", "category": "wet-food", "brand": "Acme"}
SALES = [{"month": LATEST_MONTH, "units_sold": 18}]


def test_each_level_asks_the_regression_model_for_next_months_units_at_that_price():
    fake = PriceAito()

    propose_markdown(fake, "OVER", 60, LIST_PRICE, UNIT_COST, PROFILE, SALES)

    # One `_estimate` per level, on the model the Product view's price what-if uses (ADR 0029).
    assert [c["where"]["price_eur"] for c in fake.calls] == [10.0, 9.5, 9.0, 8.5, 8.0]
    assert {c["model"] for c in fake.calls} == {"regression"}
    # The evidence is last month's units, not the unseen forecast month.
    assert all(c["where"]["units_last_month"] == 18 and "month" not in c["where"] for c in fake.calls)


def test_a_missing_estimate_is_an_error_not_a_flat_curve():
    with pytest.raises(AitoError, match="no estimate"):
        propose_markdown(PriceAito(lambda price: None), "OVER", 60, LIST_PRICE, UNIT_COST, PROFILE, SALES)
