"""A shipped snapshot is a claim about the live data; these tests say when it no longer holds.

The case that made this check: the Evaluation view shipped a snapshot that read pet-type
accuracy 0.975 while the same query on the same engine measured 0.055 (td-20260915230157220135).
Nothing noticed, because a snapshot is only compared with itself. `drifts` compares it with a
fresh run; `./do aito-check` runs both and fails on a difference.
"""

from __future__ import annotations

import pytest

from src.snapshot_drift import Headline, drifts, headline_numbers


def test_an_accuracy_far_from_the_live_one_is_reported_with_both_numbers():
    shipped = {"pet_type_from_name": Headline(0.975, tolerance=0.02)}
    live = {"pet_type_from_name": Headline(0.055, tolerance=0.02)}

    found = drifts(shipped, live)

    assert [(d.name, d.shipped, d.live) for d in found] == [("pet_type_from_name", 0.975, 0.055)]


def test_numbers_inside_their_tolerance_are_not_drift():
    shipped = {"accuracy": Headline(0.90, tolerance=0.02), "orders": Headline(8505, tolerance=0)}
    live = {"accuracy": Headline(0.91, tolerance=0.02), "orders": Headline(8505, tolerance=0)}

    assert drifts(shipped, live) == []


def test_a_count_must_match_exactly():
    shipped = {"orders": Headline(8505, tolerance=0)}
    live = {"orders": Headline(8504, tolerance=0)}

    assert [d.name for d in drifts(shipped, live)] == ["orders"]


def test_a_number_the_live_run_no_longer_has_fails_loudly_instead_of_passing():
    shipped = {"accuracy": Headline(0.9, tolerance=0.02), "dietary": Headline(0.67, tolerance=0.02)}
    live = {"accuracy": Headline(0.9, tolerance=0.02)}

    with pytest.raises(AssertionError, match="dietary"):
        drifts(shipped, live)


def test_the_overview_snapshot_is_summed_up_by_its_totals():
    overview = {"kpis": {"orders": 8505, "revenue_eur": 673834.81, "customers": 3000}}

    numbers = headline_numbers("overview", overview)

    assert numbers["orders"] == Headline(8505, tolerance=0)
    assert numbers["revenue_eur"].value == 673834.81
    assert numbers["revenue_eur"].tolerance == pytest.approx(673834.81 * 0.005)


def test_the_model_checks_file_is_summed_up_by_each_models_accuracy():
    model_checks = {
        "models": [{"id": "pet_type_from_name", "accuracy": 0.9}, {"id": "return_risk", "accuracy": 0.99}],
        "churn": {"accuracy": 0.912},
        "demand": {"accuracy": 0.4195},
    }

    numbers = headline_numbers("model-checks", model_checks)

    assert {name: h.value for name, h in numbers.items()} == {
        "pet_type_from_name": 0.9, "return_risk": 0.99, "churn": 0.912, "demand": 0.4195}


def test_an_unknown_view_is_an_error_not_an_empty_comparison():
    with pytest.raises(ValueError, match="no headline numbers for 'checkout'"):
        headline_numbers("checkout", {})
