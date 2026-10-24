"""Supply: one view's decisions from stock, Aito's forecasts and prices.

A fake client answers the four catalogue reads from a three-SKU shop and
records each `_estimate`:

  - LOW   is below its reorder point: a reorder row;
  - OVER  holds 40 units against a reorder point of 4: an overstock row;
  - MOVER sells the most: the top mover (the view lists one here), with
    stock to spare.
"""

from __future__ import annotations

import pytest

from src import cache, supply_service
from src.demand_forecast import LATEST_MONTH
from src.supply_service import get_supply

STOCK = [
    {"sku": "LOW", "current_stock": 2, "reorder_point": 10, "safety_stock": 5, "unit_cost_eur": 3.0,
     "lead_time_days": 7, "supplier": "Acme"},
    {"sku": "OVER", "current_stock": 40, "reorder_point": 4, "safety_stock": 2, "unit_cost_eur": 5.0,
     "lead_time_days": 14, "supplier": "Acme"},
    {"sku": "MOVER", "current_stock": 30, "reorder_point": 10, "safety_stock": 5, "unit_cost_eur": 2.0,
     "lead_time_days": 7, "supplier": "Acme"},
]
PRODUCTS = [{"sku": sku, "name": f"Product {sku}", "price_eur": price, "pet_type": "dog",
             "category": "treats", "brand": "Acme"} for sku, price in [("LOW", 4.0), ("OVER", 10.0), ("MOVER", 2.0)]]


def _sales(sku: str, units: int) -> list[dict]:
    return [{"product_sku": sku, "month": month, "units_sold": units, "price_eur": 1.0,
             "pet_type": "dog", "category": "treats", "brand": "Acme"} for month in ("2026-03", LATEST_MONTH)]


SALES = _sales("LOW", 12) + _sales("OVER", 1) + _sales("MOVER", 40)
# OVER sold at its list price every month but one: a list price of 10 inside its band.
STATES = ([{"product_sku": "OVER", "price_eur": 10.0}] * 7 + [{"product_sku": "OVER", "price_eur": 9.0}]
          # LOW always sold at 3, so its list price of 4 sits above the band: an outlier.
          + [{"product_sku": "LOW", "price_eur": 3.0 + 0.01 * i} for i in range(8)])


class ShopAito:
    def __init__(self):
        self.estimates: list[dict] = []

    def search(self, table, where=None, limit=10, offset=0, **_):
        rows = {"inventory": STOCK, "products": PRODUCTS, "monthly_sales": SALES, "product_states": STATES}[table]
        return {"hits": rows[offset:offset + limit], "total": len(rows)}

    def estimate(self, table, where, estimate_field, model=None, with_why=True):
        self.estimates.append({"where": where, "model": model})
        if model == "regression":                       # a markdown probe: 1 a month whatever the price
            return {"estimate": 1.0}
        return {"estimate": {"LOW": 20.0, "MOVER": 45.0}[where["product_sku"]]}


@pytest.fixture(autouse=True)
def _one_top_mover_and_no_cache(monkeypatch):
    monkeypatch.setattr(supply_service, "TOP_MOVERS", 1)
    cache.clear()
    yield
    cache.clear()


def test_the_reorder_decision_covers_the_forecast_plus_safety_stock():
    supply = get_supply(ShopAito())

    [row] = supply.reorder_queue
    assert (row.sku, row.forecast_units) == ("LOW", 20)
    assert row.order_qty == 20 + 5 - 2              # forecast + safety stock − on hand
    assert row.revenue_at_risk_eur == (20 - 2) * 4.0  # units the stock can't cover × list price
    assert supply.reorder == {"skus": 1, "units": 23, "order_cost_eur": 69.0, "revenue_at_risk_eur": 72.0}


def test_each_sku_is_forecast_once_and_overstock_gets_a_markdown_sweep():
    fake = ShopAito()

    get_supply(fake)

    knn = [e["where"]["product_sku"] for e in fake.estimates if e["model"] is None]
    assert sorted(knn) == ["LOW", "MOVER"]          # the critical SKU and the top movers
    markdown = [e["where"]["price_eur"] for e in fake.estimates if e["model"] == "regression"]
    assert markdown == [10.0, 9.5, 9.0, 8.5, 8.0]   # OVER, at 0 … 20 % off


def test_overstock_that_no_markdown_clears_is_reported_as_such():
    supply = get_supply(ShopAito())

    [row] = supply.overstock
    assert (row.sku, row.excess_units, row.tied_capital_eur) == ("OVER", 32, 160.0)
    assert row.markdown.action == "wont_clear"      # 1 a month: 32 units take far longer than a quarter
    assert supply.overstock_decision["tied_capital_eur"] == 160.0
    assert supply.overstock_decision["wont_clear"] == 1


def test_a_list_price_above_what_the_sku_sold_at_is_flagged_on_its_row_and_listed():
    supply = get_supply(ShopAito())

    assert supply.reorder_queue[0].price.outlier
    assert [o.sku for o in supply.price_outliers] == ["LOW"]
    assert supply.price_outliers[0].above_band_pct > 0
    assert not supply.overstock[0].price.outlier


def test_the_panel_shows_the_forecast_body_actually_sent():
    supply = get_supply(ShopAito())

    body = supply.last_query["body"]
    assert body["from"] == "monthly_sales" and body["estimate"] == "units_sold"
    assert body["where"]["units_last_month"] in (12, 40)
