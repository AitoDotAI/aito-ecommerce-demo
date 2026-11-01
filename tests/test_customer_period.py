"""A period set against the one just before it, of the same length (ADR 0055): both timeframes are one statistical context."""

import pytest

from src.customer_period import NoPreviousPeriod, compare, previous_period

MONTHS = [f"2026-{m:02d}" for m in range(1, 13)]


def row(months: dict[str, list], nps=()) -> dict:
    return {"months": months, "nps": [list(n) for n in nps]}


def test_the_previous_period_is_the_months_just_before_it_and_as_many():
    assert previous_period(MONTHS, "2026-04", "2026-06") == ("2026-01", "2026-03")
    assert previous_period(MONTHS, "2026-07", "2026-07") == ("2026-06", "2026-06")


def test_a_period_with_no_room_for_a_previous_one_says_so_and_does_not_shrink_it():
    with pytest.raises(NoPreviousPeriod, match="2026-01"):
        previous_period(MONTHS, "2026-03", "2026-06")


@pytest.mark.parametrize("start, end", [("2026-06", "2026-04"), ("2025-01", "2026-03"), ("2026-02", "2026-13"), ("x", "2026-03")])
def test_a_period_that_is_backwards_or_outside_the_data_is_refused(start, end):
    with pytest.raises(ValueError, match="period|month"):
        previous_period(MONTHS, start, end)


def customers(this_orders: int, previous_orders: int, n: int, revenue_each: float = 10.0) -> list[dict]:
    """`n` customers who each ordered `previous_orders` times in Jan-Mar and `this_orders` times in Apr-Jun."""
    rows = []
    for _ in range(n):
        months = {}
        for i, month in enumerate(("2026-01", "2026-02", "2026-03")):
            if i < previous_orders:
                months[month] = [1, revenue_each, revenue_each / 2]
        for i, month in enumerate(("2026-04", "2026-05", "2026-06")):
            if i < this_orders:
                months[month] = [1, revenue_each, revenue_each / 2]
        rows.append(row(months))
    return rows


def test_each_figure_is_per_customer_in_the_context_this_period_against_the_previous_one():
    rows = customers(this_orders=3, previous_orders=1, n=40)

    result = compare(rows, MONTHS, "2026-04", "2026-06")

    assert result["previous"] == {"from": "2026-01", "to": "2026-03"}
    orders = result["figures"]["orders"]
    assert (orders["this"], orders["previous"], orders["change"]) == (3.0, 1.0, 2.0)
    assert result["figures"]["revenue_eur"]["this"] == 30.0 and result["figures"]["profit_per_customer_eur"]["previous"] == 5.0


def test_a_change_the_customers_all_share_is_clear_and_one_that_is_noise_is_not():
    steady = [row({"2026-01": [1, 10.0, 5.0], "2026-04": [1, 10.0, 5.0]}) for _ in range(40)]
    noisy = [row({"2026-01": [1 + (i % 2), 10.0, 5.0]} if i % 2 else {"2026-04": [1 + (i % 3), 10.0, 5.0]}) for i in range(40)]

    assert compare(customers(3, 1, 40), MONTHS, "2026-04", "2026-06")["figures"]["orders"]["clear"] is True
    assert compare(steady, MONTHS, "2026-04", "2026-06")["figures"]["orders"]["clear"] is False
    assert compare(noisy, MONTHS, "2026-04", "2026-06")["figures"]["orders"]["margin"] > 0


def test_the_context_is_the_customers_who_ordered_in_either_timeframe_and_nobody_else():
    rows = customers(2, 1, 5) + [row({"2026-09": [1, 1.0, 1.0]})]

    result = compare(rows, MONTHS, "2026-04", "2026-06")

    assert result["context_customers"] == 5, "a customer active only in September is in neither timeframe"
    assert result["figures"]["customers"] == {"this": 5, "previous": 5, "change": 0.0, "margin": None, "clear": None, "z": None}


def test_churn_is_the_share_who_had_ordered_but_not_in_the_three_months_to_the_end_of_each_timeframe():
    stayed = [row({"2026-01": [1, 1.0, 1.0], "2026-03": [1, 1.0, 1.0], "2026-06": [1, 1.0, 1.0]}) for _ in range(30)]
    left = [row({"2026-01": [1, 1.0, 1.0], "2026-03": [1, 1.0, 1.0]}) for _ in range(30)]

    churn = compare(stayed + left, MONTHS, "2026-04", "2026-06")["figures"]["churn_rate"]

    assert churn["previous"] == 0.0 and churn["this"] == 0.5
    assert churn["change"] == pytest.approx(0.5) and churn["clear"] is True


def test_nps_needs_enough_answers_in_both_timeframes_and_is_a_difference_in_points():
    answered = [row({"2026-02": [1, 1.0, 1.0], "2026-05": [1, 1.0, 1.0]},
                    nps=[("2026-02", "detractor"), ("2026-05", "promoter")]) for _ in range(40)]
    few = [row({"2026-02": [1, 1.0, 1.0], "2026-05": [1, 1.0, 1.0]}, nps=[("2026-05", "promoter")]) for _ in range(3)]

    nps = compare(answered, MONTHS, "2026-04", "2026-06")["figures"]["nps"]

    assert (nps["previous"], nps["this"], nps["change"]) == (-100.0, 100.0, 200.0)
    assert compare(few, MONTHS, "2026-04", "2026-06")["figures"]["nps"]["this"] is None


def test_every_figure_with_a_margin_says_how_many_standard_errors_the_change_is():
    """The page names the pattern from this (Yes from 3, Likely from 2, Possibly from 1): a mean is tested at 1.96 standard errors, a share at 3."""
    rows = [row({"2026-01": [1, 10.0, 5.0], "2026-04": [1 + (i % 3), 10.0, 5.0]}) for i in range(60)]

    figures = compare(rows, MONTHS, "2026-04", "2026-06")["figures"]

    orders = figures["orders"]
    assert orders["z"] == pytest.approx(1.96 * abs(orders["change"]) / orders["margin"], rel=0.02)
    assert orders["z"] > 3 and figures["customers"]["z"] is None, "a count of customers has no margin"


def test_a_change_every_customer_made_alike_has_no_spread_and_a_capped_z():
    assert compare(customers(3, 1, 40), MONTHS, "2026-04", "2026-06")["figures"]["orders"]["z"] == 99.0


def test_a_share_is_three_standard_errors_per_margin_and_a_mean_1_96():
    stayed = [row({"2026-01": [1, 1.0, 1.0], "2026-03": [1, 1.0, 1.0], "2026-06": [1, 1.0, 1.0]}) for _ in range(30)]
    left = [row({"2026-01": [1, 1.0, 1.0], "2026-03": [1, 1.0, 1.0]}) for _ in range(30)]

    churn = compare(stayed + left, MONTHS, "2026-04", "2026-06")["figures"]["churn_rate"]

    assert churn["z"] == pytest.approx(3 * abs(churn["change"]) / churn["margin"], rel=0.01)
