"""Smart Search — the two queries the page sends, checked offline.

The live behaviour (the persona flip, no cross-pet leaks) is pinned in
tests/test_aito_check.py; the relevance gain in docs/verification/
search-eval.md. These tests pin the query shapes that produce it.
"""

from __future__ import annotations

import json

import pytest

from src import cache
from src.search_service import (
    PERSONAS, TEXT_THETA, _baseline_search, predictive_blend_body, smart_search,
)


def _product(sku: str, score: float | None = None) -> dict:
    hit = {"sku": sku, "name": f"Product {sku}", "brand": "Acme", "pet_type": "dog",
           "category": "dry-food", "price_eur": 9.9}
    if score is not None:
        hit["$score"] = score
    return hit


class FakeAito:
    def __init__(self, baseline_hits: list[dict], predictive_hits: list[dict]):
        self.baseline_hits, self.predictive_hits = baseline_hits, predictive_hits
        self.searches: list[dict] = []

    def search(self, table, **kwargs):
        self.searches.append({"table": table, **kwargs})
        hits = self.predictive_hits if kwargs.get("get") else self.baseline_hits
        return {"hits": hits, "total": len(hits)}


@pytest.fixture(autouse=True)
def _no_cache():
    cache.clear()
    yield
    cache.clear()


def test_baseline_drops_rows_that_match_no_query_word():
    """BM25's lift is exp(θ·bm25): exactly 1.0 means no word matched, and
    those rows come back in table order. Showing them would present the
    first products in the table as search results."""
    fake = FakeAito([_product("A", 2.4), _product("B", 1.3), _product("C", 1.0)], [])
    assert [h.sku for h in _baseline_search(fake, "dog food", 10)] == ["A", "B"]


def test_baseline_is_bm25_over_the_name_not_a_word_filter():
    fake = FakeAito([], [])
    _baseline_search(fake, "food for an old dog", 10)
    (call,) = fake.searches
    assert call["order_by"] == {"$similarity": {"name": "food for an old dog"}}
    assert "where" not in call or call["where"] is None


def test_predictive_blend_multiplies_purchase_probability_by_text_match():
    body = predictive_blend_body("food", PERSONAS["saara"], limit=10)
    assert body["from"] == "impressions" and body["get"] == "product_sku"
    assert body["where"] == {"customer_segment": "dog_owner", "customer_pet_size": "large"}
    assert body["orderBy"] == {"$multiply": [
        {"$p": {"$context": {"purchased": True}}},
        {"$similarity": {"name": "food"}, "theta": TEXT_THETA},
    ]}


def test_predictive_blend_has_no_candidate_filter_on_the_query_words():
    """A `$match` filter here is what capped the old column: it required
    every query word in the name, so natural phrasing returned nothing."""
    body = predictive_blend_body("food for an old dog", PERSONAS["maija"], limit=10)
    assert "$match" not in json.dumps(body)


def test_predictive_blend_does_not_select_the_blended_score():
    """`$p` in `select` would be the product of lifts (values above 1), not a
    probability; the page must never show it as one."""
    assert "$p" not in predictive_blend_body("food", PERSONAS["maija"], 10)["select"]


def test_panel_shows_the_body_the_predictive_column_actually_sent():
    fake = FakeAito([_product("A", 2.0)], [_product("A"), _product("B")])
    response = smart_search(fake, query="food", persona_id="maija", limit=10)
    assert response.last_query == {
        "endpoint": "_search", "body": predictive_blend_body("food", PERSONAS["maija"], 10)}
    (predictive_call,) = [c for c in fake.searches if c.get("get")]
    assert predictive_call["order_by"] == response.last_query["body"]["orderBy"]
    assert [h.new_entry for h in response.predictive] == [False, True]


@pytest.mark.parametrize("baseline_scores, expected", [
    ([2.0, 1.0], True),    # a name matched a query word
    ([1.0, 1.0], False),   # nothing matched: the right column is $p alone
])
def test_response_says_when_no_product_name_matched_the_query(baseline_scores, expected):
    """With no word matched, `$similarity` is 1.0 for every product and the
    predictive column ranks on purchase probability alone ("dogfood" ->
    puppy treats for a dog owner). The page must label that, not present
    it as a text match."""
    fake = FakeAito([_product(str(i), sc) for i, sc in enumerate(baseline_scores)],
                    [_product("X")])
    response = smart_search(fake, query="dogfood", persona_id="saara", limit=10)
    assert response.text_matched is expected
    assert response.to_dict()["text_matched"] is expected
