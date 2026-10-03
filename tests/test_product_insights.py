"""Offline tests for Product Insights (src/product_insights_service.py).

A fake client answers the three kinds of query the view sends: one
`_batch` of counts, one `_relate` per customer column, and a `_search` on
`monthly_sales`. The hits are in the shape `normalize_response` produces.
The live behaviour of the same queries is asserted in
`test_aito_check.py`.
"""

from __future__ import annotations

import pytest

from src import cache
from src.aito_client import AitoError
from src.product_insights_service import (
    BUYER_FIELDS, DEFAULT_SKU, UnknownProductError, get_product_insights,
)


@pytest.fixture(autouse=True)
def _no_cache():
    cache.clear()
    yield
    cache.clear()


# Funnel 363 → 139 → 112 → 90 over four surfaces, and 18 reviews.
FUNNEL = {"impressions": 363, "clicked": 139, "added_to_cart": 112, "purchased": 90}
BY_SURFACE = {"search": (128, 26), "for_you": (81, 23), "category": (125, 34), "bought_together": (29, 7)}
RATINGS = {1: 1, 2: 2, 3: 3, 4: 5, 5: 7}
SENTIMENTS = {"positive": 12, "neutral": 3, "negative": 3}


class FakeClient:
    def __init__(self, by_surface=BY_SURFACE, monthly=None):
        self.by_surface = by_surface
        self.monthly = monthly if monthly is not None else [
            {"month": "2026-01", "units_sold": 7}, {"month": "2026-03", "units_sold": 21},
        ]
        self.batches: list[list[dict]] = []
        self.relates: list[dict] = []

    def batch(self, queries):
        self.batches.append(queries)
        return [{"total": self._count(q)} for q in queries]

    def _count(self, q):
        where = dict(q["where"])
        assert q["limit"] == 0 and where.pop("product_sku") == DEFAULT_SKU
        if q["from"] == "reviews":
            if "rating" in where:
                return RATINGS[where["rating"]]
            return SENTIMENTS[where["sentiment"]]
        if "surface" in where:
            shown, bought = self.by_surface[where["surface"]]
            return bought if where.get("purchased") else shown
        step = next(iter(where), "impressions")
        return FUNNEL[step]

    def relate(self, *, table, where, relate_field, limit):
        self.relates.append({"from": table, "where": where, "relate": relate_field})
        if relate_field != "customer_segment":
            return {"hits": [_hit(relate_field, "x", 1.02, 40)]}
        return {"hits": [_hit("customer_segment", "cat_owner", 0.52, 1),
                         _hit("customer_segment", "dog_owner", 1.42, 99)]}

    def search(self, table, *, where, select, limit):
        assert table == "monthly_sales" and where == {"product_sku": DEFAULT_SKU}
        return {"hits": self.monthly}


def _hit(field, value, lift, on_condition):
    return {"related": {field: {"$has": value}}, "lift": lift,
            "fs": {"fOnCondition": on_condition, "fCondition": 117, "f": 1000, "n": 38013}}


def test_all_counts_for_a_product_go_in_one_batch():
    client = FakeClient()

    get_product_insights(client)

    # ~20 independent counts in one round-trip, each filtered to the product.
    assert len(client.batches) == 1
    assert all(q["where"]["product_sku"] == DEFAULT_SKU for q in client.batches[0])


def test_funnel_and_surfaces_come_back_as_counts():
    result = get_product_insights(FakeClient())

    assert [(s.step, s.count) for s in result.funnel] == list(FUNNEL.items())
    search = next(s for s in result.surfaces if s.surface == "search")
    assert (search.impressions, search.purchased) == (128, 26)


def test_an_unknown_surface_fails_loudly_instead_of_dropping_impressions():
    # The four known surfaces cover 300 of the 363 impressions: some
    # impressions came from a surface this view doesn't list.
    short = {**BY_SURFACE, "bought_together": (0, 0), "category": (91, 34)}
    with pytest.raises(AitoError, match="cover 300 of 363 impressions"):
        get_product_insights(FakeClient(by_surface=short))


def test_who_buys_it_relates_each_customer_column_over_the_products_order_lines():
    client = FakeClient()

    result = get_product_insights(client)

    assert sorted(r["relate"] for r in client.relates) == sorted(BUYER_FIELDS)
    assert all(r == {"from": "order_lines", "where": {"product_sku": DEFAULT_SKU}, "relate": r["relate"]}
               for r in client.relates)
    # Strongest effects first, each with the counts behind it.
    cat, dog = result.buyers[0], result.buyers[1]
    assert (cat.value, cat.lift, cat.lines, cat.lines_total) == ("cat_owner", 0.52, 1, 117)
    assert (dog.value, dog.lift, dog.lines) == ("dog_owner", 1.42, 99)


def test_query_pane_shows_the_relate_body_that_was_sent():
    client = FakeClient()

    result = get_product_insights(client)

    assert result.last_query["body"] in client.relates


def test_months_without_a_sales_row_show_as_zero_units():
    result = get_product_insights(FakeClient())

    assert [(m.month, m.units_sold) for m in result.monthly] == [
        ("2026-01", 7), ("2026-02", 0), ("2026-03", 21),
    ]


def test_reviews_are_counted_by_rating_and_sentiment():
    result = get_product_insights(FakeClient())

    assert result.ratings == {str(r): n for r, n in RATINGS.items()}
    assert result.sentiments == SENTIMENTS


def test_an_unknown_product_is_rejected_before_any_query():
    client = FakeClient()

    with pytest.raises(UnknownProductError):
        get_product_insights(client, sku="SKU-DOES-NOT-EXIST")
    assert client.batches == [] and client.relates == []


def test_links_to_bought_together_for_the_products_category():
    # Puppy Cheese Treats is a dog treat; Bought Together has no "dog treats"
    # anchor, so there is no link rather than a link to the wrong category.
    result = get_product_insights(FakeClient())

    assert result.bought_together_anchor is None
