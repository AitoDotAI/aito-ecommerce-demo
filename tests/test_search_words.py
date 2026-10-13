"""Offline tests for Shop analytics' search words (src/search_words.py),
with the fake client from test_shop_analytics.py."""

from __future__ import annotations

import json

import pytest

from src.aito_client import AitoError
from src.search_words import SEARCH, SEARCH_PURCHASED, get_search_words_section, together_count_query
from tests.test_shop_analytics import FakeClient, hit, key


def words(bought, shown, counts=None):
    return FakeClient({key("impressions", SEARCH_PURCHASED, "search_query"): bought,
                       key("impressions", SEARCH, "search_query"): shown}, counts=counts)


def bought_hit(word, purchases):
    return hit("search_query", word, 3.0, purchases, 4_000, 0, 115_000)


def shown_hit(word, impressions):
    return hit("search_query", word, 3.0, impressions, 40_000, impressions, 115_000)


def test_a_words_lift_is_against_search_impressions_not_all_impressions():
    # 4,000 of 40,000 search impressions end in a purchase (10 %).
    # "cheese": 140 purchases of 560 impressions (25 %), so 2.5×.
    # "food": 1,600 of 16,000 (10 %), so 1.0×, though Aito's lift against
    # all 115,000 impressions would read about 2.9×.
    client = words([bought_hit("cheese", 140), bought_hit("food", 1_600)],
                   [shown_hit("cheese", 560), shown_hit("food", 16_000)])

    section = get_search_words_section(client)

    assert [(w.word, w.lift, w.purchases, w.impressions) for w in section.rows] == [("cheese", 2.5, 140, 560)]
    assert (section.search_impressions, section.search_purchases) == (40_000, 4_000)


def test_only_words_with_enough_independent_purchases_are_tested():
    client = words([bought_hit("cheese", 140), bought_hit("rare", 12)],
                   [shown_hit("cheese", 560), shown_hit("rare", 40)])

    section = get_search_words_section(client)

    assert (section.words, section.significance.tested) == (2, 1)


def test_a_word_never_bought_is_listed_with_the_purchases_the_average_expects():
    client = words([bought_hit("cheese", 140)], [shown_hit("cheese", 560), shown_hit("clipper", 70)])

    section = get_search_words_section(client)

    assert [(w.word, w.impressions, w.expected_purchases) for w in section.never_bought] == [("clipper", 70, 7.0)]


def test_words_always_searched_together_are_one_phrase_in_their_order():
    together = json.dumps(together_count_query(("algae", "wafers")), sort_keys=True)
    client = words([bought_hit("algae", 33), bought_hit("wafers", 33)],
                   [shown_hit("algae", 154), shown_hit("wafers", 154)],
                   counts={together: (154, "algae wafers")})

    section = get_search_words_section(client)

    assert section.words == 1 and [w.word for w in section.rows] == ["algae wafers"]


def test_words_with_equal_counts_that_are_not_searched_together_stay_apart():
    together = json.dumps(together_count_query(("blend", "budgie")), sort_keys=True)
    client = words([bought_hit("cheese", 140)],
                   [shown_hit("cheese", 560), shown_hit("blend", 20), shown_hit("budgie", 20)],
                   counts={together: (0, "unused")})

    section = get_search_words_section(client)

    assert sorted(w.word for w in section.never_bought) == ["blend", "budgie"]


def test_a_word_bought_from_search_but_never_shown_there_fails_loudly():
    client = words([bought_hit("cheese", 70)], [shown_hit("food", 16_000)])

    with pytest.raises(AitoError, match="cheese"):
        get_search_words_section(client)
