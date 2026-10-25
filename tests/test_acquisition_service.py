"""The Acquisition view's rates and the answers it refuses to read loosely (ADR 0040)."""

import pytest

from src.acquisition_service import source_row, wilson
from src.aito_client import AitoError


def test_a_small_cohort_gets_a_wide_interval_that_stays_inside_zero_and_one():
    small, large = wilson(3, 10), wilson(300, 1000)

    assert 0.0 <= small.low < small.share < small.high <= 1.0
    assert small.high - small.low > large.high - large.low
    assert wilson(0, 20).low == 0.0 and wilson(20, 20).high == 1.0


def test_a_rate_over_no_rows_fails_loudly():
    with pytest.raises(AitoError, match="no interval"):
        wilson(0, 0)


def answers(*, regular_lift=1.37, true_hit=True):
    hit = {"feature": True, "$p": 0.7,
           "$why": {"factors": [{"type": "relatedPropositionLift", "proposition": {"first_source": "organic_search"},
                                 "value": regular_lift}]}}
    return [{"total": 970}, {"total": 30}, {"total": 100}, {"total": 70},
            {"hits": [hit] if true_hit else [{"feature": False, "$p": 0.3}]}]


def landing(category="toys", lift=2.5):
    return [{"related": {"landing_category": {"$has": category}}, "lift": lift},
            {"related": {"landing_category": {"$has": "wet-food"}}, "lift": 0.5}]


def test_a_source_row_reads_conversion_regulars_the_prediction_and_where_visitors_land():
    row = source_row("organic_search", answers(), landing())

    assert (row.sessions, row.conversion.successes) == (1000, 30)
    assert (row.labelled_customers, row.regular.successes) == (100, 70)
    assert (row.predicted_regular, row.source_lift) == (0.7, 1.37)
    assert [(l.category, l.lift) for l in row.landing] == [("toys", 2.5)]


def test_a_prediction_without_a_true_hit_or_without_the_sources_lift_fails_loudly():
    with pytest.raises(AitoError, match="no `true` hit"):
        source_row("organic_search", answers(true_hit=False), landing())
    wrong = answers()
    wrong[4]["hits"][0]["$why"]["factors"] = []
    with pytest.raises(AitoError, match="expected one"):
        source_row("organic_search", wrong, landing())
