"""The Shop's product drawer (src/shop_product.py), against a fake Aito."""

import pytest

from src.lookup_errors import UnknownProductError
from src.shop_product import get_product_drawer


def pair(sku, lift, together, with_it=92):
    return {"related": {"skus": {"$has": sku}}, "lift": lift,
            "fs": {"fOnCondition": together, "fCondition": with_it, "f": 300, "n": 12000}}


class FakeAito:
    def __init__(self, pairs):
        self.pairs = pairs
        self.searches: list[tuple[str, dict]] = []

    def search(self, table, *, where, limit=10, **_):
        self.searches.append((table, where))
        if table == "products":
            skus = where["sku"]["$or"] if isinstance(where["sku"], dict) else [where["sku"]]
            return {"hits": [{"sku": s, "name": f"Name {s}"} for s in skus if s != "NOPE"]}
        return {"hits": [{"month": "2026-02"}, {"month": "2025-11"}]}

    def relate(self, table, where, relate_field, limit=10):
        assert (table, relate_field, where) == ("orders", "skus", {"skus": {"$match": "SKU-A"}})
        return {"hits": self.pairs}


def test_same_basket_keeps_well_supported_pairs_and_drops_the_product_itself():
    fake = FakeAito([pair("SKU-A", 126.0, 92), pair("SKU-B", 4.0, 30), pair("SKU-C", 6.5, 3)])

    drawer = get_product_drawer(fake, "SKU-A", "helena")

    # SKU-C's 6.5× rests on 3 orders: too few to call "often", whatever the interval.
    assert [(p.sku, p.together, p.orders_with_it) for p in drawer.same_basket] == [("SKU-B", 30, 92)]
    assert drawer.same_basket[0].name == "Name SKU-B"


def test_your_orders_are_the_shoppers_own_history_in_time_order():
    fake = FakeAito([])

    drawer = get_product_drawer(fake, "SKU-A", "helena")

    assert ("orders", {"customer_id": "CUST-00053", "skus": {"$match": "SKU-A"}}) in fake.searches
    assert drawer.your_orders == ["2025-11", "2026-02"]


def test_an_unknown_product_is_refused():
    with pytest.raises(UnknownProductError, match="NOPE"):
        get_product_drawer(FakeAito([]), "NOPE", "helena")
