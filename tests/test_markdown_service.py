"""Markdown — what each markdown probe asks Aito.

Offline: a fake client answers from one overstocked SKU and records each
`_estimate`. Markdown probes the same "units next month at this price"
question as the Price view's demand curve, so the two pin the same
evidence: last month's units, not the unseen forecast month. A probe that
gets no estimate is an error, not the SKU's average.
"""

from __future__ import annotations

import pytest

from src import cache
from src.aito_client import AitoError
from src.demand_forecast import LATEST_MONTH
from src.markdown_service import MARKDOWN_LEVELS_PCT, get_markdowns


INVENTORY = [{"sku": "OVER", "current_stock": 400, "reorder_point": 20, "unit_cost_eur": 4.0}]
PRODUCTS = [{"sku": "OVER", "name": "Cat Wet Food", "price_eur": 10.0,
             "pet_type": "cat", "category": "wet-food", "brand": "Acme"}]


def _sales(month: str, units: int) -> dict:
    return {"product_sku": "OVER", "month": month, "units_sold": units, "price_eur": 10.0,
            "pet_type": "cat", "category": "wet-food", "brand": "Acme"}


class MarkdownAito:
    def __init__(self, estimate: float | None = 30.0):
        self.estimate_value = estimate
        self.estimate_wheres: list[dict] = []

    def search(self, table, where=None, limit=10, offset=0, **_):
        rows = {"inventory": INVENTORY, "products": PRODUCTS,
                "monthly_sales": [_sales("2026-03", 25), _sales(LATEST_MONTH, 18)]}[table]
        return {"hits": rows[offset:offset + limit], "total": len(rows)}

    def estimate(self, table, where, estimate_field, with_why=True):
        self.estimate_wheres.append(where)
        return {"estimate": self.estimate_value}


@pytest.fixture(autouse=True)
def _no_cache():
    cache.clear()
    yield
    cache.clear()


def test_markdown_probes_condition_on_last_months_units_not_the_unseen_month():
    fake = MarkdownAito()

    get_markdowns(fake)

    assert len(fake.estimate_wheres) == len(MARKDOWN_LEVELS_PCT)
    assert all("month" not in w for w in fake.estimate_wheres)
    assert {w["units_last_month"] for w in fake.estimate_wheres} == {18}
    # 0 %, 5 %, … 20 % off the list price of 10.
    assert sorted(w["price_eur"] for w in fake.estimate_wheres) == [8.0, 8.5, 9.0, 9.5, 10.0]


def test_a_probe_without_an_estimate_fails_instead_of_using_the_average():
    """The probe used to swap in the SKU's mean monthly units, so a missing
    estimate looked like a flat demand curve: the price cut "sold" nothing
    extra, and the proposal rested on a number Aito never gave."""
    with pytest.raises(AitoError, match="no estimate"):
        get_markdowns(MarkdownAito(estimate=None))


def test_markdown_panel_shows_the_query_shape_actually_sent():
    response = get_markdowns(MarkdownAito())

    where = response.last_query["body"]["where"]
    assert "month" not in where
    assert "units_last_month" in where and "price_eur" in where
