"""The Reviews view's sections and the reply comparison (ADR 0039)."""

import pytest

from src.design_effect import DesignEffect
from src.reviews_service import get_reply_effect, get_reviews_section

NO_CLUSTERING = DesignEffect(customers=100, rows_per_customer=1.0, intra_customer_correlation=0.0, design_effect=1.0)


class CountingClient:
    """Answers `_search limit 0` with the totals of a table of customer-months who wrote a negative review."""

    def __init__(self, replied: tuple[int, int], unreplied: tuple[int, int]):
        self.totals = {(True, False): replied[0], (True, True): replied[1],
                       (False, False): unreplied[0], (False, True): unreplied[1]}

    def search(self, table, *, where, limit):
        assert table == "customer_months" and limit == 0 and where["had_negative_review"] is True
        return {"total": self.totals[(where["review_replied"], "churned_in_3_months" in where)]}


def test_a_reply_with_fewer_leavers_is_a_tie_while_the_interval_spans_one():
    # 23 of 398 against 33 of 398: the ratio is 0.70, its interval spans 1.
    client = CountingClient(replied=(398, 23), unreplied=(398, 33))

    effect = get_reply_effect(client, NO_CLUSTERING)

    assert effect.risk_ratio == pytest.approx(0.697, abs=0.001)
    assert effect.interval_low < 1 < effect.interval_high
    assert effect.verdict == "a tie"


def test_a_clear_difference_says_who_leaves_and_clustering_widens_the_interval():
    client = CountingClient(replied=(4000, 100), unreplied=(4000, 400))
    clustered = DesignEffect(customers=100, rows_per_customer=20.0, intra_customer_correlation=0.5, design_effect=10.0)

    plain = get_reply_effect(client, NO_CLUSTERING)
    wide = get_reply_effect(client, clustered)

    assert plain.verdict == "fewer leave" and plain.interval_high < 1
    assert wide.interval_high - wide.interval_low > plain.interval_high - plain.interval_low


def test_an_unknown_section_is_refused():
    with pytest.raises(ValueError, match="section"):
        get_reviews_section(None, "revenue")
