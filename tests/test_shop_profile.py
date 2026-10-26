"""The Shop's shopper profile (src/shop_profile.py), against a fake Aito: the customer row and the
orders before the month, read as they are."""

import pytest

from src.shop_profile import get_shopper_profile
from tests.fake_shop_aito import FakeShopAito, product

ORDERS = [{"month": "2025-06", "skus": "SKU-Z", "total_eur": 10.0},
          {"month": "2025-11", "skus": "SKU-A", "total_eur": 20.5},
          {"month": "2026-02", "skus": "SKU-A SKU-Z", "total_eur": 30.0},
          {"month": "2026-05", "skus": "SKU-A", "total_eur": 99.0}]    # not yet: the month asked is April


class FakeAito(FakeShopAito):
    def __init__(self, orders=ORDERS, catalogue=True):
        super().__init__([])
        self.orders, self.catalogue = orders, catalogue

    def search(self, table, *, where=None, limit=10, **kwargs):
        if table == "orders":
            return {"hits": self.orders, "total": len(self.orders)}
        if table == "products":
            skus = where["sku"]["$or"] if isinstance(where["sku"], dict) else [where["sku"]]
            return {"hits": [{**product(s), "name": f"Name {s}"} for s in skus] if self.catalogue else []}
        return super().search(table, where=where, limit=limit, **kwargs)


def test_the_profile_reads_the_orders_before_the_month_newest_first():
    profile = get_shopper_profile(FakeAito(), "janne", "2026-04")

    assert [o.month for o in profile.history] == ["2026-02", "2025-11", "2025-06"]
    assert profile.orders_total == 3 and profile.spent_eur == 60.5    # the May order hasn't happened
    assert profile.last_basket.items == ["Name SKU-A", "Name SKU-Z"]


def test_it_says_what_the_customer_declared_and_what_the_shop_read():
    declared = get_shopper_profile(FakeAito(), "janne", "2026-04")
    assert (declared.pets, declared.pets_declared, declared.diet) == ("dog", True, "grain-free")

    read = get_shopper_profile(FakeAito(), "eemil", "2026-04")
    assert read.pets_declared is False and read.pets    # no declared pets: the pets are those of their orders


def test_a_shopper_with_no_orders_has_no_last_basket():
    profile = get_shopper_profile(FakeAito(orders=[]), "helena", "2026-04")

    assert profile.last_basket is None and profile.history == [] and profile.orders_total == 0


def test_an_order_with_a_product_not_in_the_catalogue_is_named():
    with pytest.raises(LookupError, match="not in the catalogue"):
        get_shopper_profile(FakeAito(catalogue=False), "janne", "2026-04")
