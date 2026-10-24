"""A product's demand curve (src/price_curve.py): next month's units at
seven prices, from `_estimate units_sold` with the regression model.

Offline: a fake client answers the product, its unit cost and its sales,
and records each `_estimate`. These pin what each estimate conditions on.
"""

from __future__ import annotations

import pytest

from src import cache
from src.aito_client import AitoError
from src.demand_forecast import LATEST_MONTH
from src.lookup_errors import UnknownProductError
from src.price_curve import get_price_curve


@pytest.fixture(autouse=True)
def _no_cache():
    cache.clear()
    yield
    cache.clear()


PRODUCT = {"sku": "REAL", "name": "Chicken Dog Food", "pet_type": "dog", "category": "dry-food",
           "brand": "Acme", "price_eur": 14.00}

def _sales(month: str, units: int, price: float) -> dict:
    return {"product_sku": "REAL", "month": month, "units_sold": units, "price_eur": price,
            "revenue_eur": units * price, "pet_type": "dog", "category": "dry-food",
            "brand": "Acme", "season": "spring"}


SALES = [_sales("2026-03", 9, 10.0), _sales(LATEST_MONTH, 12, 9.8)]


class CurveAito:
    """Answers the curve's lookups and records each `_estimate`."""

    def __init__(self, sales: list[dict] = SALES, estimate: float | None = 11.0):
        self.sales = sales
        self.estimate_value = estimate
        self.estimate_wheres: list[dict] = []
        self.estimate_models: list[str | None] = []

    def search(self, table, where=None, limit=10, offset=0, **_):
        rows = {"monthly_sales": self.sales,
                "inventory": [{"sku": "REAL", "unit_cost_eur": 6.0}],
                "products": [PRODUCT] if where == {"sku": "REAL"} else []}[table]
        return {"hits": rows[offset:offset + limit], "total": len(rows)}

    def estimate(self, table, where, estimate_field, model=None, with_why=True):
        assert (table, estimate_field) == ("monthly_sales", "units_sold")
        self.estimate_wheres.append(where)
        self.estimate_models.append(model)
        return {"estimate": self.estimate_value}


def test_demand_curve_conditions_on_last_months_units_not_the_unseen_month():
    """`month: "2026-05"` matches no training row, so it is no evidence and
    the estimate fell back to the SKU's all-time average. Last month's
    units are the evidence, as in the Demand forecast (ADR 0014)."""
    fake = CurveAito()

    get_price_curve(fake, "REAL")

    assert len(fake.estimate_wheres) == 7                     # one per price
    assert all("month" not in w for w in fake.estimate_wheres)
    assert {w["units_last_month"] for w in fake.estimate_wheres} == {12}
    assert len({w["price_eur"] for w in fake.estimate_wheres}) == 7


def test_a_sku_that_sold_nothing_last_month_is_estimated_from_zero_units():
    """No row for the latest month means it sold nothing then."""
    fake = CurveAito(sales=[_sales("2026-03", 9, 10.0)])

    get_price_curve(fake, "REAL")

    assert {w["units_last_month"] for w in fake.estimate_wheres} == {0}


def test_demand_curve_panel_shows_a_query_that_was_actually_sent():
    fake = CurveAito()

    result = get_price_curve(fake, "REAL")

    assert result.last_query["body"]["where"] in fake.estimate_wheres


def test_demand_curve_fails_loudly_when_aito_returns_no_estimate():
    with pytest.raises(AitoError, match="no estimate"):
        get_price_curve(CurveAito(estimate=None), "REAL")


def test_demand_curve_uses_the_regression_model_like_the_what_if():
    # ADR 0029: the what-if explains a price with the regression model, so
    # the curve asks the same model and a point on it matches the what-if.
    client = CurveAito()

    get_price_curve(client, "REAL")

    assert client.estimate_models and set(client.estimate_models) == {"regression"}


def test_the_curve_centres_on_the_average_selling_price_and_prices_profit_at_unit_cost():
    # Sold at €10.00 and €9.80: the centre is €9.90, the unit cost €6.00.
    result = get_price_curve(CurveAito(), "REAL")

    centre = next(p for p in result.curve if p.adjustment_pct == 0)
    assert centre.price_eur == 9.9
    assert centre.profit_eur == round((9.9 - 6.0) * 11.0, 2)
    assert [p.adjustment_pct for p in result.curve] == [-10, -7, -3, 0, 3, 7, 10]


def test_an_unknown_product_is_a_lookup_error_not_an_empty_curve():
    with pytest.raises(UnknownProductError):
        get_price_curve(CurveAito(), "NOPE")
