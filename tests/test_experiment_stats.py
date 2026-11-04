"""The arithmetic behind the Experiments page: profit per showing, the difference of two arms with its interval, and the gain of a policy."""
import random

import pytest

from src.experiment_stats import MIN_GAIN, arm_figures, bootstrap_gain, personal_choice_verdict, profit_difference, verdict


def test_an_arms_profit_per_showing_is_its_purchase_rate_times_its_margin():
    figures = arm_figures(shown=1000, bought=50, margin_eur=8.0)
    assert figures == {"showings": 1000, "purchases": 50, "rate": 0.05, "profit_per_showing": pytest.approx(0.4)}


def test_a_clearly_better_second_arm_has_an_interval_above_zero():
    result = profit_difference((10000, 500), (10000, 800), 8.0, 8.0)
    assert result["delta"] == pytest.approx(0.24) and result["interval"][0] > 0
    assert verdict(result) == "second arm better"


def test_a_discount_that_sells_more_can_still_earn_less_because_the_margin_is_lower():
    result = profit_difference((10000, 500), (10000, 650), 8.0, 5.0)   # 30 % more purchases, 37 % less margin
    assert result["delta"] < 0 and verdict(result) == "control better"


def test_a_small_difference_over_few_showings_is_not_clear():
    result = profit_difference((200, 10), (200, 13), 8.0, 8.0)
    assert result["interval"][0] < 0 < result["interval"][1] and verdict(result) == "no clear difference"


def test_a_policy_that_earns_more_has_a_positive_gain_and_a_random_tie_straddles_zero():
    better = {f"C{i}": [(1.0, 1.1)] for i in range(200)}
    assert bootstrap_gain(better, random.Random(1))["gain_percent"] == pytest.approx(10.0)
    assert bootstrap_gain(better, random.Random(1))["interval_percent"][0] > 9
    rng = random.Random(2)
    tie = {f"C{i}": [(1.0 + rng.gauss(0, 0.2), 1.0 + rng.gauss(0, 0.2))] for i in range(200)}
    low, high = bootstrap_gain(tie, random.Random(1))["interval_percent"]
    assert low < 0 < high


def test_choosing_per_person_needs_a_gain_that_is_enough_and_an_interval_above_zero_and_a_smaller_real_gain_is_named_so():
    assert personal_choice_verdict({"gain_percent": MIN_GAIN + 1, "interval_percent": [0.5, 7.0]}) == "choose per person"
    assert personal_choice_verdict({"gain_percent": MIN_GAIN + 1, "interval_percent": [-0.5, 7.0]}) == "keep the plain winner"
    assert personal_choice_verdict({"gain_percent": MIN_GAIN - 1, "interval_percent": [0.5, 3.0]}) == "small gain"
    assert personal_choice_verdict({"gain_percent": 0.1, "interval_percent": [-0.5, 0.7]}) == "keep the plain winner"
