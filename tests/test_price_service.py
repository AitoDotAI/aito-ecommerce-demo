"""Price view — which findings it is allowed to show.

Offline: a fake client answers from a tiny price history. These pin the
two rules that keep the view from presenting noise as a finding: an
"outlier" needs enough history to have a band, and a "sweet spot" needs
enough support for its lift to be distinguishable from 1. The demand
curve tests pin what each `_estimate` conditions on.
"""

from __future__ import annotations

import pytest

from src import cache
from src.aito_client import AitoError
from src.demand_forecast import LATEST_MONTH
from src.price_service import get_price_detail, get_prices


def _prices(sku: str, values: list[float]) -> list[dict]:
    return [{"product_sku": sku, "price_eur": v, "discount_pct": 0.0} for v in values]


PRODUCTS = [
    # Two observations, list price far above them: looks like an outlier,
    # but a band from two points means nothing.
    {"sku": "THIN", "name": "Cage Cover", "pet_type": "small_animal",
     "category": "accessories", "price_eur": 18.77},
    # Twelve observations tightly around 10, list price 14: a real outlier.
    {"sku": "REAL", "name": "Chicken Dog Food", "pet_type": "dog",
     "category": "dry-food", "price_eur": 14.00},
    # Twelve observations around 5, list price inside the band.
    {"sku": "FAIR", "name": "Cat Litter", "pet_type": "cat",
     "category": "litter", "price_eur": 5.00},
]
HISTORY = (
    _prices("THIN", [17.37, 17.79])
    + _prices("REAL", [9.8, 10.0, 10.2] * 4)
    + _prices("FAIR", [4.8, 5.0, 5.2] * 4)
)


def _relate_hit(category: str, lift: float, f_on: int, f_cond: int, f: int, n: int) -> dict:
    return {"related": {"product_sku.category": {"$has": category}}, "lift": lift,
            "fs": {"fOnCondition": f_on, "fCondition": f_cond, "f": f, "n": n},
            "ps": {"pOnCondition": f_on / f_cond, "p": f / n}}


class FakeAito:
    def search(self, table, where=None, limit=10, offset=0, **_):
        rows = {"price_history": HISTORY, "products": PRODUCTS}[table]
        return {"hits": rows[offset:offset + limit], "total": len(rows)}

    def aggregate(self, table, where, aggregate_fields):
        return {"mean": 10.0}

    def relate(self, table, where, relate_field, limit=10):
        return {"hits": [
            # Big lift, tiny support: indistinguishable from 1.
            _relate_hit("grooming", 1.66, f_on=11, f_cond=1000, f=66, n=10000),
            # Enough support to pass the floor, but lift 1.17 on 35 rows has
            # a 95 % interval of about [0.83, 1.65]: the interval decides.
            _relate_hit("health", 1.17, f_on=35, f_cond=1000, f=300, n=10000),
            # Modest lift, huge support: a real effect.
            _relate_hit("toys", 1.30, f_on=390, f_cond=1000, f=3000, n=10000),
        ]}


@pytest.fixture(autouse=True)
def _no_cache():
    cache.clear()
    yield
    cache.clear()


def test_a_sku_with_two_observations_is_never_flagged_as_an_outlier():
    """The live view opened on exactly this: a cage cover whose "band"
    came from two sales (demo review, 2026-09-28)."""
    bands = {b.sku: b for b in get_prices(FakeAito()).fair_bands}
    assert bands["THIN"].outlier is False


def test_a_well_supported_outlier_is_still_flagged_and_listed_first():
    response = get_prices(FakeAito())
    assert {b.sku: b.outlier for b in response.fair_bands}["REAL"] is True
    assert response.fair_bands[0].sku == "REAL"
    assert response.summary["outlier_skus"] == 1


def test_a_sweet_spot_needs_a_lift_distinguishable_from_one():
    """Grooming's 1.66 rests on 11 rows; its 95 % interval spans 1. Toys'
    1.30 rests on 390; its interval excludes 1. Only toys is a finding."""
    spots = get_prices(FakeAito()).sweet_spots
    assert {s.category for s in spots} == {"toys"}


def test_a_supported_sweet_spot_is_still_rejected_when_its_interval_spans_one():
    """Support alone isn't enough: health has 35 rows (over the floor of
    30), but its lift of 1.17 can't be told apart from 1. This exercises
    the interval itself, so a wrong sign or term in the standard error
    fails here, not just a wrong support threshold."""
    categories = {s.category for s in get_prices(FakeAito()).sweet_spots}
    assert "health" not in categories
    assert "toys" in categories


# ── Demand curve: `_estimate units_sold` at seven prices ─────────────


def _sales(month: str, units: int, price: float) -> dict:
    return {"product_sku": "REAL", "month": month, "units_sold": units, "price_eur": price,
            "revenue_eur": units * price, "pet_type": "dog", "category": "dry-food",
            "brand": "Acme", "season": "spring"}


SALES = [_sales("2026-03", 9, 10.0), _sales(LATEST_MONTH, 12, 9.8)]


class CurveAito:
    """Answers the detail view's lookups and records each `_estimate`."""

    def __init__(self, sales: list[dict] = SALES, estimate: float | None = 11.0):
        self.sales = sales
        self.estimate_value = estimate
        self.estimate_wheres: list[dict] = []

    def search(self, table, where=None, limit=10, offset=0, **_):
        rows = {"monthly_sales": self.sales,
                "inventory": [{"sku": "REAL", "unit_cost_eur": 6.0}],
                "products": [p for p in PRODUCTS if p["sku"] == "REAL"]}[table]
        return {"hits": rows[offset:offset + limit], "total": len(rows)}

    def estimate(self, table, where, estimate_field, with_why=True):
        assert (table, estimate_field) == ("monthly_sales", "units_sold")
        self.estimate_wheres.append(where)
        return {"estimate": self.estimate_value}


def test_demand_curve_conditions_on_last_months_units_not_the_unseen_month():
    """`month: "2026-05"` matches no training row, so it is no evidence and
    the estimate fell back to the SKU's all-time average. Last month's
    units are the evidence, as in the Demand forecast (ADR 0014)."""
    fake = CurveAito()

    get_price_detail(fake, "REAL")

    assert len(fake.estimate_wheres) == 7                     # one per price
    assert all("month" not in w for w in fake.estimate_wheres)
    assert {w["units_last_month"] for w in fake.estimate_wheres} == {12}
    assert len({w["price_eur"] for w in fake.estimate_wheres}) == 7


def test_a_sku_that_sold_nothing_last_month_is_estimated_from_zero_units():
    """No row for the latest month means it sold nothing then."""
    fake = CurveAito(sales=[_sales("2026-03", 9, 10.0)])

    get_price_detail(fake, "REAL")

    assert {w["units_last_month"] for w in fake.estimate_wheres} == {0}


def test_demand_curve_panel_shows_a_query_that_was_actually_sent():
    fake = CurveAito()

    detail = get_price_detail(fake, "REAL")

    assert detail.last_query["body"]["where"] in fake.estimate_wheres


def test_demand_curve_fails_loudly_when_aito_returns_no_estimate():
    with pytest.raises(AitoError, match="no estimate"):
        get_price_detail(CurveAito(estimate=None), "REAL")
