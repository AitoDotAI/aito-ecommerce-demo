"""How the personalised-search benchmark scores and words a result (ADR 0037 §3).

Pure functions, no Aito: the reference BM25, the per-session scores, the
paired comparisons and the sentences the page shows. The wording tests are
the rules of ADR 0037 §2 as executable examples.
"""

from __future__ import annotations

import pytest

from src.backtest_metrics import Interval
from src.personalised_search.bm25 import Bm25, tokens
from src.personalised_search.metrics import (BM25, BM25_REFERENCE, GENERATOR, HISTORY, HOUSEHOLD, RANKINGS, SHOP,
                                             Comparison, all_scores, first_hit_rank, hit_at_10, reciprocal_rank,
                                             slice_scores)
from src.personalised_search.sessions import history_slice
from src.personalised_search.wording import Verdict, comparison_sentence, headline, points, verdict


# ── The reference BM25 ───────────────────────────────────────────────


def test_bm25_tokens_are_lower_cased_letter_and_digit_runs():
    assert tokens("Grain-Free Puppy Food 2kg") == ["grain", "free", "puppy", "food", "2kg"]


def test_bm25_ranks_the_name_holding_the_rarer_word_first():
    # "salmon" is in one name, "food" in all three: the rare word carries the score.
    index = Bm25({"a": "Chicken Cat Food", "b": "Salmon Cat Food", "c": "Beef Dog Food"})
    assert index.ranked("salmon food") == ["b", "a", "c"]


def test_bm25_leaves_out_names_without_a_query_word():
    index = Bm25({"a": "Chicken Cat Food", "b": "Dog Leash"})
    assert index.ranked("cat") == ["a"]


def test_bm25_favours_the_shorter_name_for_the_same_word():
    # Length normalisation (b = 0.75): one match in a short name beats one in a long name.
    index = Bm25({"short": "Cat Bowl", "long": "Cat Bowl Ceramic Large Blue Deluxe"})
    assert index.ranked("cat") == ["short", "long"]


# ── Per-session scores ───────────────────────────────────────────────


def test_first_hit_rank_is_the_rank_of_the_first_product_bought():
    assert first_hit_rank(["x", "y", "z"], frozenset({"z", "y"})) == 2
    assert first_hit_rank(["x"], frozenset({"z"})) is None


def test_hit_at_10_and_reciprocal_rank_from_a_first_hit_rank():
    assert (hit_at_10(10), hit_at_10(11), hit_at_10(None)) == (1.0, 0.0, 0.0)
    assert (reciprocal_rank(4), reciprocal_rank(None)) == (0.25, 0.0)


@pytest.mark.parametrize("orders, name", [(0, "0"), (1, "1-2"), (2, "1-2"), (3, "3-5"), (5, "3-5"), (6, "6+")])
def test_history_slices_are_the_adrs_0_1_2_3_5_6_plus(orders, name):
    assert history_slice(orders) == name


def _rows(n: int, ranks: dict[str, int | None], slice_name: str = "1-2") -> list[dict]:
    return [{"session": f"S{i}", "slice": slice_name, "ranks": {r: ranks.get(r) for r in RANKINGS}}
            for i in range(n)]


def test_the_three_preregistered_comparisons_in_order():
    rows = _rows(20, {SHOP: 1, HISTORY: 3, GENERATOR: 1}) + _rows(20, {BM25: 2, HOUSEHOLD: 4, GENERATOR: 1})
    scores = slice_scores("1-2", rows)
    assert [(c.ranking, c.against) for c in scores.comparisons] == [
        (SHOP, BM25), (HISTORY, SHOP), (GENERATOR, scores.best_aito)]


def test_best_aito_ranking_goes_to_the_shops_search_on_a_tie():
    rows = _rows(40, {SHOP: 1, HISTORY: 1, HOUSEHOLD: 1})
    assert slice_scores("all", rows).best_aito == SHOP


def test_all_scores_puts_every_session_first_then_each_slice_with_sessions():
    rows = _rows(5, {SHOP: 1}, "0") + _rows(5, {SHOP: 1}, "6+")
    assert [s.name for s in all_scores(rows)] == ["all", "0", "6+"]


# ── Wording (ADR 0037 §2) ────────────────────────────────────────────


def _scores_with(sessions: int, difference: Interval, shop=0.6, bm25=0.5):
    rows = _rows(sessions, {})
    scores = slice_scores("3-5", rows)
    hit10 = {**scores.hit10, SHOP: Interval(shop, shop - 0.05, shop + 0.05), BM25: Interval(bm25, bm25 - 0.05, bm25 + 0.05)}
    comparison = Comparison(SHOP, BM25, difference)
    return scores.__class__(scores.name, sessions, hit10, scores.mrr, SHOP, [comparison]), comparison


def test_an_interval_spanning_zero_is_a_tie():
    scores, c = _scores_with(100, Interval(0.02, -0.01, 0.05))
    assert verdict(100, c) is Verdict.TIE
    assert comparison_sentence(scores, c) == (
        "3–5 prior orders: Aito, the Shop's search and BM25 are a tie. "
        "hit@10 60.0% vs 50.0%, difference +2.0 pp [-1.0, +5.0]; the interval spans 0.")


def test_a_lead_is_worded_only_when_the_interval_excludes_zero():
    scores, c = _scores_with(100, Interval(0.10, 0.04, 0.16))
    assert "Aito, the Shop's search is ahead of BM25" in comparison_sentence(scores, c)


def test_a_lead_for_the_baseline_names_the_baseline_first():
    scores, c = _scores_with(100, Interval(-0.10, -0.16, -0.04), shop=0.4, bm25=0.5)
    assert comparison_sentence(scores, c).startswith("3–5 prior orders: BM25 is ahead of Aito, the Shop's search.")


def test_a_slice_under_30_sessions_is_too_few_to_read_even_with_a_clear_interval():
    scores, c = _scores_with(29, Interval(0.30, 0.20, 0.40))
    sentence = comparison_sentence(scores, c)
    assert verdict(29, c) is Verdict.TOO_FEW
    assert "too few to read" in sentence and "ahead" not in sentence


def test_the_index_headline_is_the_shops_search_against_bm25_without_the_slice_label():
    scores, _ = _scores_with(100, Interval(0.02, -0.01, 0.05))
    assert headline(scores).startswith("Aito, the Shop's search and BM25 are a tie.")


def test_differences_are_shown_in_percentage_points():
    assert points(Interval(0.042, 0.02, 0.064)) == "+4.2 pp [+2.0, +6.4]"


def test_reference_bm25_is_a_ranking_but_not_compared():
    # It shows the left column is a standard BM25; it isn't a contender.
    assert BM25_REFERENCE in RANKINGS
    scores = slice_scores("all", _rows(40, {}))
    assert all(BM25_REFERENCE not in (c.ranking, c.against) for c in scores.comparisons)
