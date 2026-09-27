"""The search-evaluation harness — its metrics and its judgments.

Offline: fixtures only, no Aito. These tests exist so the harness can be
trusted before it is used to compare systems. Each pins a property that,
if broken, would silently make the evaluation report the wrong thing.
"""

from __future__ import annotations

import math

from src.search_eval.metrics import (
    mrr, ndcg_at_k, paired_bootstrap_ci, precision_at_k, recall_at_k,
)
from src.search_eval.relevance import grade, judge, load_products, load_queries

P = {"sku": "x", "name": "Royal Canin Senior Chicken Dog Food 2kg",
     "pet_type": "dog", "category": "dry-food", "dietary": "senior", "brand": "Royal Canin"}


# ── metrics ──────────────────────────────────────────────────────────


def test_ndcg_is_one_for_the_ideal_ranking_and_zero_for_nothing_relevant():
    labels = {"a": 2, "b": 1}
    assert math.isclose(ndcg_at_k(["a", "b", "c"], labels), 1.0)
    assert ndcg_at_k(["c", "d"], labels) == 0.0


def test_ndcg_penalises_what_was_not_retrieved():
    """The ideal ranking is built from ALL relevant products, so finding one
    of three relevant items cannot score as perfect."""
    labels = {"a": 2, "b": 2, "c": 2}
    assert ndcg_at_k(["a"], labels) < 0.5


def test_ndcg_rewards_putting_the_better_item_first():
    labels = {"full": 2, "part": 1}
    assert ndcg_at_k(["full", "part"], labels) > ndcg_at_k(["part", "full"], labels)


def test_precision_recall_and_mrr():
    labels = {"a": 2, "b": 1, "c": 2}
    ranked = ["z", "a", "b", "y", "x"]
    assert precision_at_k(ranked, labels, 5) == 2 / 5
    assert recall_at_k(ranked, labels, 20) == 1 / 2    # grade-2 only: a found, c not
    assert mrr(ranked, labels) == 1 / 2                # first grade-2 at rank 2
    assert mrr([], labels) == 0.0


def test_bootstrap_interval_excludes_zero_only_for_a_real_difference():
    same = [0.5] * 30
    d, lo, hi = paired_bootstrap_ci(same, same)
    assert d == 0 and lo <= 0 <= hi
    d, lo, hi = paired_bootstrap_ci([0.2] * 30, [0.6] * 30)
    assert lo > 0


# ── judgments ────────────────────────────────────────────────────────


def test_grade_is_two_when_every_constraint_holds():
    q = {"pet": "dog", "categories": ["dry-food"], "refine": {"dietary": "senior"}}
    assert grade(q, P) == 2


def test_grade_is_one_when_only_the_refinement_fails():
    q = {"pet": "dog", "categories": ["dry-food"], "refine": {"dietary": "puppy"}}
    assert grade(q, P) == 1


def test_brand_only_query_gives_no_partial_credit():
    """Without a pet/category core, 'partially relevant' would mean every
    product in the shop — so it must be all or nothing."""
    assert grade({"refine": {"brand": "Whiskas"}}, P) == 0
    assert grade({"refine": {"brand": "Royal Canin"}}, P) == 2


def test_wrong_pet_is_irrelevant_whatever_the_refinement():
    q = {"pet": "cat", "refine": {"brand": "Royal Canin"}}
    assert grade(q, P) == 0


def test_every_query_in_the_set_is_judgeable():
    """A query with no fully relevant product cannot distinguish systems —
    it would only add noise, so the set must not contain one."""
    products = load_products()
    for q in load_queries():
        assert 2 in judge(q, products).values(), f"{q['id']} ({q['q']}) has no relevant product"


def test_query_set_covers_all_six_strata_evenly():
    from collections import Counter
    c = Counter(q["stratum"] for q in load_queries())
    assert set(c) == {"exact", "brand", "synonym", "paraphrase", "misspelling", "nordic"}
    assert set(c.values()) == {10}


def test_labels_do_not_come_from_the_text_being_searched():
    """The paraphrase stratum must include products whose NAME lacks the
    refinement word — otherwise it only tests keyword matching. Here: senior
    dog food whose name does not say 'senior'."""
    products = load_products()
    q = next(q for q in load_queries() if q["id"] == "p01")
    full = [p for p in products if grade(q, p) == 2]
    assert any("senior" not in p["name"].lower() for p in full)
