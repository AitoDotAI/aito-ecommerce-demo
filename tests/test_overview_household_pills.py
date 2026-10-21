"""Dashboard household pills are derived from the numbers each card shows.

The pills used to be hand-written per group ("High AOV" on the group with
the lowest basket). Now a pill only states a rank the card's own share or
average basket proves.
"""

from __future__ import annotations

from src.overview_service import _rank_pill

# Shares and baskets as the observable dataset's dashboard shows them.
SHARES = {"dog": 42.1, "cat": 29.8, "dog cat": 15.2, "small_animal": 7.3, "aquarium": 5.6}
BASKETS = {"dog": 74.34, "cat": 74.74, "dog cat": 108.38, "small_animal": 119.48, "aquarium": 63.05}


def test_the_group_with_the_highest_average_basket_is_pilled_highest_basket():
    assert _rank_pill("small_animal", SHARES, BASKETS) == ("Highest basket", "orange")


def test_the_group_with_the_lowest_average_basket_is_pilled_lowest_basket():
    assert _rank_pill("aquarium", SHARES, BASKETS) == ("Lowest basket", "grey")


def test_the_largest_group_is_pilled_largest_group():
    assert _rank_pill("dog", SHARES, BASKETS) == ("Largest group", "blue")


def test_a_group_that_ranks_on_nothing_gets_no_pill():
    assert _rank_pill("cat", SHARES, BASKETS) is None
    assert _rank_pill("dog cat", SHARES, BASKETS) is None
