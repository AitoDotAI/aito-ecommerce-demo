"""The Shop grid (src/shop_grid.py), against a fake Aito.

The live behaviour of the same queries is checked in test_aito_check.py
on the ADR 0030 test env.
"""

import pytest

from src.aito_client import AitoError
from src.lookup_errors import UnknownProductError
from src.shop_grid import get_shop_grid

CUSTOMERS = {
    "CUST-00049": {"customer_id": "CUST-00049", "segment": "dog_owner", "lifestyle": "mid",
                   "health_focus": "high", "treat_affinity": "low", "brand_loyalty": "loyal",
                   "diet_rule": "grain-free"},
    "CUST-00053": {"customer_id": "CUST-00053", "segment": "cat_owner", "lifestyle": "mid",
                   "health_focus": "medium", "treat_affinity": "medium", "brand_loyalty": "flexible"},
}


def product(sku, p=0.0, category="dry-food"):
    return {"sku": sku, "name": f"Brand {sku}", "brand": "Brand", "pet_type": "cat",
            "category": category, "price_eur": 4.0, "$p": p}


class FakeAito:
    def __init__(self, ranked, last_order="SKU-B SKU-X", reasked_p=0.02):
        self.ranked = ranked
        self.last_order = last_order
        self.reasked_p = reasked_p
        self.recommends: list[dict] = []
        self.batches: list[list[dict]] = []

    def search(self, table, *, where, limit=10, **_):
        if table == "customers":
            return {"hits": [CUSTOMERS[where["customer_id"]]]}
        if table == "products":
            return {"hits": [product(s) for s in where["sku"]["$or"] if s.startswith("SKU-")]}
        return {"hits": [{"month": "2026-03", "skus": self.last_order}, {"month": "2025-11", "skus": "SKU-OLD"}]}

    def recommend(self, table, where, recommend_field, goal, limit=8):
        self.recommends.append(where)
        return {"hits": self.ranked}

    def batch(self, queries):
        self.batches.append(queries)
        return [{"hits": [{"feature": False, "$p": 1 - self.reasked_p}, {"feature": True, "$p": self.reasked_p}]}
                for _ in queries]


def test_a_household_rule_is_a_filter_on_the_candidates():
    fake = FakeAito([product("SKU-A", 0.5)])

    grid = get_shop_grid(fake, "janne", "2026-04", [])

    assert grid.rule == "grain-free"
    assert {"product_sku.name": {"$match": "Grain"}} in fake.recommends[0]["$or"]


def test_the_carts_items_are_context_and_are_not_recommended_again():
    fake = FakeAito([product("SKU-A", 0.5)])

    get_shop_grid(fake, "helena", "2026-04", ["SKU-C"])

    where = fake.recommends[0]
    assert where["product_sku"] == {"$not": {"$or": ["SKU-C"]}}
    assert where["basket_skus"] == {"$and": [{"$match": "SKU-C"}]}


def test_an_item_bought_last_order_is_reasked_as_just_bought_and_falls():
    # SKU-B ranks first, but the shopper bought it last order; Aito's answer
    # for "just bought" (0.02) drops it below SKU-A.
    fake = FakeAito([product("SKU-B", 0.6), product("SKU-A", 0.5)])

    grid = get_shop_grid(fake, "helena", "2026-04", [])

    [query] = fake.batches[0]
    assert query["where"]["product_sku"] == "SKU-B" and query["where"]["just_bought"] is True
    assert [i.sku for i in grid.items] == ["SKU-A", "SKU-B"]
    assert grid.items[1].p == 0.02 and grid.items[1].p_if_new == 0.6


def test_the_last_order_is_the_latest_one_before_the_month():
    fake = FakeAito([product("SKU-A", 0.5)])

    assert get_shop_grid(fake, "helena", "2026-04", []).last_order_skus == ["SKU-B", "SKU-X"]
    assert get_shop_grid(fake, "helena", "2026-01", []).last_order_skus == ["SKU-OLD"]


def test_a_cart_item_that_does_not_exist_is_refused():
    with pytest.raises(UnknownProductError, match="NOPE-1"):
        get_shop_grid(FakeAito([]), "helena", "2026-04", ["NOPE-1"])


def test_a_predict_without_a_true_answer_raises():
    fake = FakeAito([product("SKU-B", 0.6)])
    fake.batch = lambda queries: [{"hits": [{"feature": False, "$p": 1.0}]}]

    with pytest.raises(AitoError, match="no `true` hit"):
        get_shop_grid(fake, "helena", "2026-04", [])
