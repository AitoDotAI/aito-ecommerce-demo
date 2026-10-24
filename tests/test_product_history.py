"""Product › History (src/product_history.py): one product's record, in one `_batch`.

A fake client answers the batch: twelve `_search limit 0` counts (funnel
and surfaces), then the product's reviews, states and monthly sales as
rows, in the shape `_batch` returns them. The live behaviour of the same
queries is asserted in `test_aito_check.py`.
"""

from __future__ import annotations

import pytest

from src.aito_client import AitoError
from src.product_history import ROWS_LIMIT, get_product_history

SKU = "SKU-PT-0192"

FUNNEL = {"impressions": 363, "clicked": 139, "added_to_cart": 112, "purchased": 90}
BY_SURFACE = {"search": (128, 26), "for_you": (81, 23), "category": (125, 34), "bought_together": (29, 7)}
REVIEWS = [
    {"created_at": "2026-02", "rating": 5, "sentiment": "positive"},
    {"created_at": "2026-02", "rating": 4, "sentiment": "positive"},
    {"created_at": "2026-03", "rating": 2, "sentiment": "negative"},
]


def state(month: str, **changes) -> dict:
    return {"product_sku": SKU, "month": month, "price_eur": 2.79, "list_price_eur": 2.78,
            "discount_band": "none", "rating_band": "4", "age": "established",
            "rival_launched": False, "price_change": "none", **changes}


STATES = [state("2026-01"), state("2026-02", discount_band="15-20", price_eur=2.24), state("2026-03")]
# No row for February: it sold nothing then.
SALES = [{"month": "2026-01", "units_sold": 7}, {"month": "2026-03", "units_sold": 21}]


class FakeClient:
    def __init__(self, by_surface=BY_SURFACE, reviews=REVIEWS, states=STATES, sales=SALES):
        self.by_surface = by_surface
        self.tables = {"reviews": reviews, "product_states": states, "monthly_sales": sales}
        self.batches: list[list[dict]] = []

    def batch(self, queries):
        self.batches.append(queries)
        return [self._answer(q) for q in queries]

    def _answer(self, q):
        where = dict(q["where"])
        assert where.pop("product_sku") == SKU
        if q["limit"] > 0:
            rows = self.tables[q["from"]]
            return {"total": len(rows), "hits": rows[:q["limit"]]}
        if "context.surface" in where:
            shown, bought = self.by_surface[where["context.surface"]]
            return {"total": bought if where.get("purchased") else shown, "hits": []}
        return {"total": FUNNEL[next(iter(where), "impressions")], "hits": []}


def test_the_whole_record_comes_back_in_one_batch():
    client = FakeClient()

    get_product_history(client, SKU)

    # Fifteen independent reads, one round-trip, each filtered to the product.
    assert len(client.batches) == 1 and len(client.batches[0]) == 15


def test_funnel_and_surfaces_come_back_as_counts():
    history = get_product_history(FakeClient(), SKU)

    assert [(s.step, s.count) for s in history.funnel] == list(FUNNEL.items())
    search = next(s for s in history.surfaces if s.surface == "search")
    assert (search.impressions, search.purchased) == (128, 26)


def test_each_month_on_sale_carries_its_units_state_and_reviews():
    months = get_product_history(FakeClient(), SKU).months

    assert [(m.month, m.units_sold, m.discount_band, m.reviews) for m in months] == [
        ("2026-01", 7, "none", 0),
        ("2026-02", 0, "15-20", 2),   # no sales row: 0 units, not a missing month
        ("2026-03", 21, "none", 1),
    ]


def test_reviews_are_counted_by_rating_and_sentiment():
    history = get_product_history(FakeClient(), SKU)

    assert history.ratings == {"1": 0, "2": 1, "3": 0, "4": 1, "5": 1}
    assert history.sentiments == {"positive": 2, "neutral": 0, "negative": 1}


def test_an_unknown_surface_fails_loudly_instead_of_dropping_impressions():
    # The four known surfaces cover 300 of the 363 impressions.
    short = {**BY_SURFACE, "bought_together": (0, 0), "category": (91, 34)}
    with pytest.raises(AitoError, match="cover 300 of 363 impressions"):
        get_product_history(FakeClient(by_surface=short), SKU)


def test_a_sale_in_a_month_with_no_state_fails_loudly():
    with pytest.raises(AitoError, match="no product_states row"):
        get_product_history(FakeClient(sales=[*SALES, {"month": "2026-04", "units_sold": 3}]), SKU)


def test_rows_beyond_the_limit_fail_instead_of_being_cut_off():
    many = [REVIEWS[0]] * (ROWS_LIMIT + 1)
    with pytest.raises(AitoError, match="only 500 came back"):
        get_product_history(FakeClient(reviews=many), SKU)
