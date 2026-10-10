"""Inventory's reorder queue uses the shared demand forecast.

The Aito reads are replaced with fixed rows, so this checks the view's own
arithmetic: a critical SKU is forecast with `forecast_units` (the same
function Demand uses), and the reorder quantity is built from it.
"""

import pytest

from src import cache
from src import inventory_service


SKU = "SKU-PT-0177"
INVENTORY_ROW = {
    "sku": SKU, "current_stock": 2, "reorder_point": 10, "safety_stock": 5,
    "unit_cost_eur": 1.5, "lead_time_days": 7, "supplier": "Acme",
}
PRODUCT = {"name": "Puppy Cheese Treats", "pet_type": "dog", "category": "dog-treats",
           "brand": "Nordic", "price_eur": 4.0}
SALES = [{"month": "2026-04", "units_sold": 12, "pet_type": "dog",
          "category": "dog-treats", "brand": "Nordic"}]


@pytest.fixture
def one_critical_sku(monkeypatch):
    monkeypatch.setattr(cache, "get", lambda key: None)
    monkeypatch.setattr(cache, "set", lambda *args, **kwargs: None)
    monkeypatch.setattr(inventory_service, "_fetch_all_inventory", lambda client: [INVENTORY_ROW])
    monkeypatch.setattr(inventory_service, "_fetch_products", lambda client: {SKU: PRODUCT})
    monkeypatch.setattr(inventory_service, "_fetch_recent_sales", lambda client: {SKU: SALES})
    monkeypatch.setattr(inventory_service, "forecast_units",
                        lambda client, sku, history: (20, None))


def test_critical_sku_reorder_quantity_covers_the_forecast_plus_safety_stock(one_critical_sku):
    response = inventory_service.get_inventory(client=None)

    [row] = response.reorder_queue
    assert row.forecast_units == 20
    # forecast 20 + safety stock 5 - stock on hand 2
    assert row.suggested_reorder_qty == 23
    # 18 units short at €4.00 retail
    assert row.revenue_at_risk_eur == 72.0
