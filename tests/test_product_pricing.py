"""The Pricing tab's numbers (src/product_pricing.py), against a fake Aito: a list price becomes a price index,
the index an `_estimate units_index`, and the product's own months say where an answer may be given."""

import pytest

from src.lookup_errors import ProductNotOnSaleError, UnknownProductError
from src.product_pricing import CURVE_INDEXES, get_product_pricing

# A product listed at €10.00 with 4 offered, sold at price indexes from 0.90 to 1.00 in 8 months.
STATE = {"list_price_eur": 10.0, "list_price_index": 1.0, "discount_pct": 0.0, "on_offer": False}
MONTHS = [{"month": f"2026-0{m}", "price_index": 0.90 + 0.0125 * m, "units_sold": 4, "units_index": 1.0}
          for m in range(1, 9)]


class FakeAito:
    """Units fall 2 % of the mean for every 0.01 of price index above 0.90."""

    def __init__(self, state=STATE, sales=MONTHS, inventory=({"unit_cost_eur": 6.0},)):
        self.state, self.sales, self.inventory = state, sales, list(inventory)
        self.estimated: list[float] = []

    def search(self, table, *, where=None, limit=10, **_):
        rows = {"products": [{"sku": "SKU-1", "name": "Dog food"}], "product_states": [self.state],
                "inventory": self.inventory, "monthly_sales": self.sales}[table]
        return {"hits": rows}

    def estimate(self, table, where, field, *, model=None, with_why=True):
        assert (table, field, model) == ("monthly_sales", "units_index", "regression")
        self.estimated.append(where["price_index"])
        return {"estimate": 1.0 - 2.0 * (where["price_index"] - 0.90)}


def test_the_curve_asks_aito_for_units_at_each_list_price_and_scales_by_the_products_mean():
    fake = FakeAito()

    pricing = get_product_pricing(fake, "SKU-1", "2026-09")

    assert [p.list_price_index for p in pricing.curve] == list(CURVE_INDEXES)
    assert sorted(fake.estimated) == sorted(CURVE_INDEXES)         # no offer: the effective index is the list index
    at_list = next(p for p in pricing.curve if p.list_price_index == 1.0)
    assert at_list.units == pytest.approx(0.8 * 4.0)               # 1.0 - 2 * 0.10 = 0.8 of a mean of 4 units
    assert at_list.profit_eur == pytest.approx(at_list.units * (10.0 - 6.0))


def test_an_offer_lowers_the_price_a_shopper_pays_and_the_index_asked():
    offered = {**STATE, "discount_pct": 20.0, "on_offer": True}
    fake = FakeAito(state=offered)

    pricing = get_product_pricing(fake, "SKU-1", "2026-09")

    assert 0.8 in fake.estimated                                     # list index 1.0 less 20 %
    at_list = next(p for p in pricing.curve if p.list_price_index == 1.0)
    assert (at_list.price_eur, at_list.price_index) == (8.0, 0.8)


def test_a_price_beyond_what_the_product_has_sold_at_is_not_answered_and_cannot_be_best():
    pricing = get_product_pricing(FakeAito(), "SKU-1", "2026-09")

    out = [p for p in pricing.curve if not p.in_range]
    assert {p.list_price_index for p in out} == {0.85, 1.10, 1.15}   # tried 0.9125-1.00, answered to 0.8625-1.05
    assert pricing.best is not None and pricing.best.in_range
    assert pricing.best.profit_eur == max(p.profit_eur for p in pricing.curve if p.in_range)


def test_a_list_price_the_owner_types_becomes_a_point_beside_the_curve():
    pricing = get_product_pricing(FakeAito(), "SKU-1", "2026-09", list_price_eur=9.3)

    assert pricing.asked is not None and pricing.asked.list_price_index == 0.93
    assert pricing.asked not in pricing.curve


def test_a_product_that_sold_nothing_before_the_month_has_no_units_to_scale():
    never = [{**m, "units_sold": 0, "units_index": None} for m in MONTHS]

    pricing = get_product_pricing(FakeAito(sales=never), "SKU-1", "2026-09")

    assert pricing.mean_units is None and pricing.best is None
    assert all(p.units == 0 for p in pricing.curve)


def test_a_product_without_a_state_that_month_is_refused():
    class NoState(FakeAito):
        def search(self, table, **kw):
            return {"hits": []} if table == "product_states" else super().search(table, **kw)

    with pytest.raises(ProductNotOnSaleError):
        get_product_pricing(NoState(), "SKU-1", "2026-09")


def test_an_unknown_product_is_refused():
    class NoProduct(FakeAito):
        def search(self, table, **kw):
            return {"hits": []} if table == "products" else super().search(table, **kw)

    with pytest.raises(UnknownProductError):
        get_product_pricing(NoProduct(), "SKU-9", "2026-09")
