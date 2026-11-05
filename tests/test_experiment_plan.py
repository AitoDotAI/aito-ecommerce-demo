"""What-if controls for an experiment (ADR 0064, slice 3): what a chosen split, floor and guardrail would mean, from the arms' counted evidence."""
import pytest

from src.experiment_plan import plan

# Control: 5 % buy, €8 a sale = €0.40 a showing. Second arm: 6.5 % buy, €8 a sale = €0.52 a showing, over 2 000 showings each (4 months).
CLEAR = {"arms": [{"arm": "a", "showings": 2000, "purchases": 100, "margin_eur": 8.0}, {"arm": "b", "showings": 2000, "purchases": 130, "margin_eur": 8.0}]}
# The same rates over 200 showings each: far too few to tell apart.
THIN = {"arms": [{"arm": "a", "showings": 200, "purchases": 10, "margin_eur": 8.0}, {"arm": "b", "showings": 200, "purchases": 13, "margin_eur": 8.0}]}
# The second arm sells more (7.5 %) but earns €4 a sale: €0.30 a showing against €0.40.
WORSE = {"arms": [{"arm": "a", "showings": 20000, "purchases": 1000, "margin_eur": 8.0}, {"arm": "b", "showings": 20000, "purchases": 1500, "margin_eur": 4.0}]}


def test_profit_a_month_is_the_showings_times_the_split_weighted_profit_per_showing():
    result = plan(CLEAR, months=4, allocation=0.25, floor=0.1, guardrail_percent=10)
    # 1 000 showings a month; a quarter on the second arm.
    assert result["monthly_showings"] == 1000
    assert result["testing"]["profit_per_month"] == pytest.approx(1000 * (0.75 * 0.40 + 0.25 * 0.52))
    assert result["all_control"]["profit_per_month"] == pytest.approx(400)


def test_deciding_the_better_arm_keeps_the_floor_on_the_other_and_earns_more_than_testing_on():
    result = plan(CLEAR, months=4, allocation=0.5, floor=0.1, guardrail_percent=10)
    assert result["decided"]["arm"] == "b"
    assert result["decided"]["profit_per_month"] == pytest.approx(1000 * (0.9 * 0.52 + 0.1 * 0.40))
    assert result["decided"]["profit_per_month"] > result["testing"]["profit_per_month"]
    assert result["cost_of_testing_per_month"] == pytest.approx(result["decided"]["profit_per_month"] - result["testing"]["profit_per_month"])


def test_a_more_lopsided_split_takes_longer_to_get_a_clear_answer():
    even = plan(THIN, months=4, allocation=0.5, floor=0.1, guardrail_percent=10)["months_to_clear"]
    lopsided = plan(THIN, months=4, allocation=0.4, floor=0.1, guardrail_percent=10)["months_to_clear"]
    assert 0 < even < lopsided


def test_an_already_clear_difference_needs_no_more_months():
    assert plan(CLEAR, months=4, allocation=0.5, floor=0.1, guardrail_percent=10)["months_to_clear"] == 0


def test_a_difference_too_small_to_find_in_three_years_says_so_instead_of_a_number():
    assert plan(THIN, months=4, allocation=0.5, floor=0.1, guardrail_percent=10)["months_to_clear"] > 0
    nearly_equal = {"arms": [CLEAR["arms"][0], {**CLEAR["arms"][1], "purchases": 101}]}
    assert plan(nearly_equal, months=4, allocation=0.5, floor=0.1, guardrail_percent=10)["months_to_clear"] is None


def test_the_guardrail_trips_when_the_second_arm_is_clearly_worse_by_more_than_the_limit():
    assert plan(WORSE, months=4, allocation=0.5, floor=0.1, guardrail_percent=10)["guardrail"]["trips"] is True
    assert plan(WORSE, months=4, allocation=0.5, floor=0.1, guardrail_percent=60)["guardrail"]["trips"] is False   # worse by 25 %, within 60 %
    assert plan(CLEAR, months=4, allocation=0.5, floor=0.1, guardrail_percent=10)["guardrail"]["trips"] is False


@pytest.mark.parametrize("kwargs", [{"allocation": 0.0}, {"allocation": 1.0}, {"floor": -0.1}, {"floor": 0.6}, {"guardrail_percent": 0}, {"guardrail_percent": 101}])
def test_a_split_floor_or_guardrail_out_of_range_is_refused_with_the_range(kwargs):
    settings = {"allocation": 0.5, "floor": 0.1, "guardrail_percent": 10, **kwargs}
    with pytest.raises(ValueError, match="between"):
        plan(CLEAR, months=4, **settings)


def test_an_experiment_with_no_showings_has_nothing_to_plan_from():
    draft = {"arms": [{"arm": "a", "showings": 0, "purchases": 0, "margin_eur": 8.0}, {"arm": "b", "showings": 0, "purchases": 0, "margin_eur": 8.0}]}
    with pytest.raises(ValueError, match="no showings"):
        plan(draft, months=4, allocation=0.5, floor=0.1, guardrail_percent=10)
