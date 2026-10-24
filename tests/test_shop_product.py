"""The Shop's product drawer (src/shop_product.py), against a fake Aito."""

import pytest

from src.lookup_errors import UnknownProductError
from src.shop_product import get_product_drawer
from tests.fake_shop_aito import FakeShopAito, product


def pair(sku, lift, together, with_it=92):
    return {"related": {"skus": {"$has": sku}}, "lift": lift,
            "fs": {"fOnCondition": together, "fCondition": with_it, "f": 300, "n": 12000}}


class FakeAito(FakeShopAito):
    def __init__(self, pairs, alternatives=(), offers=None):
        super().__init__(list(alternatives), offers=offers)
        self.pairs = pairs
        self.searches: list[tuple[str, dict]] = []

    def search(self, table, *, where=None, limit=10, **kwargs):
        self.searches.append((table, where))
        if table == "products":
            skus = where["sku"]["$or"] if isinstance(where["sku"], dict) else [where["sku"]]
            return {"hits": [{**product(s), "name": f"Name {s}"} for s in skus if s != "NOPE"]}
        if table == "orders":
            orders = [{"month": "2025-06", "skus": "SKU-Z"}, {"month": "2025-11", "skus": "SKU-A"},
                      {"month": "2026-02", "skus": "SKU-A SKU-Z"}, {"month": "2026-05", "skus": "SKU-A"}]
            return {"hits": orders, "total": len(orders)}
        return super().search(table, where=where, limit=limit, **kwargs)

    def relate(self, table, where, relate_field, limit=10):
        assert (table, relate_field, where) == ("orders", "skus", {"skus": {"$match": "SKU-A"}})
        return {"hits": self.pairs}


def test_same_basket_keeps_well_supported_pairs_and_drops_the_product_itself():
    fake = FakeAito([pair("SKU-A", 126.0, 92), pair("SKU-B", 4.0, 30), pair("SKU-C", 6.5, 3)])

    drawer = get_product_drawer(fake, "SKU-A", "helena", "2026-04", [])

    # SKU-C's 6.5× rests on 3 orders: too few to call "often", whatever the interval.
    assert [(p.sku, p.together, p.orders_with_it) for p in drawer.same_basket] == [("SKU-B", 30, 92)]
    assert drawer.same_basket[0].name == "Name SKU-B"


def test_your_orders_are_the_shoppers_own_history_before_the_month():
    fake = FakeAito([])

    drawer = get_product_drawer(fake, "SKU-A", "helena", "2026-04", [])

    # The 2026-05 order hasn't happened yet in April 2026; the 2025-06 one didn't hold it.
    assert ("orders", {"customer_id": "CUST-00053"}) in fake.searches
    assert drawer.your_orders == ["2025-11", "2026-02"]


def test_an_unknown_product_is_refused():
    with pytest.raises(UnknownProductError, match="NOPE"):
        get_product_drawer(FakeAito([]), "NOPE", "helena", "2026-04", [])


def test_alternatives_are_the_same_kind_of_product_ranked_for_this_shopper():
    fake = FakeAito([], alternatives=[product("SKU-ALT", 0.4)], offers={"SKU-A": 17.5})

    drawer = get_product_drawer(fake, "SKU-A", "helena", "2026-04", ["SKU-C"])

    where = fake.recommends[0]
    assert (where["product_sku.category"], where["product_sku.pet_type"]) == ("dry-food", "cat")
    assert where["product_sku"] == {"$not": {"$or": ["SKU-C", "SKU-A"]}}   # the cart, and itself
    assert [a.sku for a in drawer.alternatives] == ["SKU-ALT"]
    assert drawer.offer_pct == 17.5


def test_a_kit_items_alternatives_are_the_same_kind_of_kit():
    # "accessories" holds cages and bottles alike: a bottle's alternatives are bottles.
    fake = FakeAito([])
    fake.search = lambda table, *, where=None, limit=10, **kw: (
        {"hits": [{**product("SKU-A", category="accessories", pet_type="small_animal"),
                   "name": "PetNord Water Bottle 500ml", "brand": "PetNord"}]}
        if table == "products" and where == {"sku": "SKU-A"} else FakeAito.search(fake, table, where=where, limit=limit, **kw))

    get_product_drawer(fake, "SKU-A", "helena", "2026-04", [])

    assert fake.recommends[0]["product_sku.name"] == {"$match": "Water Bottle"}


def test_a_sku_of_the_products_own_name_is_no_alternative_and_twins_show_once():
    # SKU-A is "Name SKU-A" (the fake's catalogue); SKU-TWIN shares that name.
    fake = FakeAito([], alternatives=[product("SKU-TWIN", 0.5, name="Name SKU-A"),
                                      product("SKU-ALT", 0.4, name="Other Hideout"),
                                      product("SKU-ALT2", 0.3, name="Other Hideout")])

    drawer = get_product_drawer(fake, "SKU-A", "helena", "2026-04", [])

    assert [(a.sku, a.same_name_skus) for a in drawer.alternatives] == [("SKU-ALT", ["SKU-ALT2"])]
