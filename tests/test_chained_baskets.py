"""Chained baskets (ADR 0047): the links the loader derives, and what they promise."""

from collections import Counter

import pytest

from src.chained_baskets import link_contexts, link_orders
from src.data_loader import load_fixture
from src.schema import SCHEMAS
from src.shop_context import basket_words

PRODUCTS = {
    "SKU-1": {"sku": "SKU-1", "pet_type": "small_animal", "category": "accessories", "name": "PetNord Cage, large", "brand": "PetNord"},
    "SKU-2": {"sku": "SKU-2", "pet_type": "small_animal", "category": "dry-food", "name": "PetNord Pellets 1kg", "brand": "PetNord"},
}


def order(order_id, customer, month, skus="SKU-2"):
    return {"order_id": order_id, "customer_id": customer, "month": month, "skus": skus}


ORDERS = [order("ORD-1", "C1", "2025-01", "SKU-1 SKU-2"), order("ORD-2", "C1", "2025-03"),
          order("ORD-3", "C2", "2025-02"), order("ORD-4", "C1", "2025-03"), order("ORD-5", "C1", "2025-06")]


def test_an_order_points_to_the_customers_order_before_it():
    linked = {o["order_id"]: o for o in link_orders(ORDERS, PRODUCTS)}

    assert "previous_order" not in linked["ORD-1"] and "previous_order" not in linked["ORD-3"]   # first orders
    assert linked["ORD-2"]["previous_order"] == "ORD-1"
    assert linked["ORD-4"]["previous_order"] == "ORD-2"      # the same month chains by order_id
    assert linked["ORD-5"]["previous_order"] == "ORD-4"


def test_an_order_carries_its_words_in_the_contexts_vocabulary():
    linked = {o["order_id"]: o for o in link_orders(ORDERS, PRODUCTS)}

    assert linked["ORD-1"]["basket_categories"].split() == basket_words([PRODUCTS["SKU-1"], PRODUCTS["SKU-2"]])
    assert "small_animal_cage" in linked["ORD-1"]["basket_categories"].split()


def test_a_context_points_to_the_latest_order_of_an_earlier_month_never_its_own():
    contexts = [{"context_id": "X1", "customer": "C1", "month": "2025-03"},     # sees ORD-1 only: ORD-2/4 are its month
                {"context_id": "X2", "customer": "C1", "month": "2025-04"},     # sees ORD-4, the later of March's two
                {"context_id": "X3", "customer": "C1", "month": "2025-01"},     # nothing before January
                {"context_id": "X4", "visitor": "V9", "month": "2025-04"}]      # not identified

    linked = {c["context_id"]: c for c in link_contexts(contexts, ORDERS)}

    assert linked["X1"]["last_order"] == "ORD-1" and linked["X2"]["last_order"] == "ORD-4"
    assert "last_order" not in linked["X3"] and "last_order" not in linked["X4"]


def test_the_schema_loads_orders_before_what_links_to_them():
    names = list(SCHEMAS)
    assert names.index("orders") < names.index("contexts") < names.index("impressions")
    assert SCHEMAS["orders"]["columns"]["previous_order"]["link"] == "orders.order_id"
    assert SCHEMAS["contexts"]["columns"]["last_order"]["link"] == "orders.order_id"


# The fixtures themselves: the properties ADR 0047's acceptance criteria name.

@pytest.fixture(scope="module")
def loaded():
    orders, contexts = load_fixture("orders"), load_fixture("contexts")
    return orders, contexts, {o["order_id"]: o for o in orders}


def test_every_order_but_a_customers_first_has_a_previous_order_that_is_theirs_and_earlier(loaded):
    orders, _, by_id = loaded
    firsts = {c: min(o["month"] for o in orders if o["customer_id"] == c) for c in {o["customer_id"] for o in orders}}

    for o in orders:
        before = by_id.get(o.get("previous_order"))
        if before is None:
            assert o["month"] == firsts[o["customer_id"]] or o.get("previous_order") is None
            continue
        assert before["customer_id"] == o["customer_id"] and (before["month"], before["order_id"]) < (o["month"], o["order_id"])
        assert before["order_id"] < o["order_id"]      # a link target loads before the order that links to it


def test_each_customers_orders_form_one_chain_without_a_fork_or_a_cycle(loaded):
    orders, _, _ = loaded
    successors = Counter(o["previous_order"] for o in orders if "previous_order" in o)
    assert successors.most_common(1)[0][1] == 1                                    # no two orders share a predecessor
    heads = Counter(o["customer_id"] for o in orders if "previous_order" not in o)
    assert set(heads.values()) == {1}                                              # one first order per customer


def test_no_context_links_to_an_order_of_its_own_month_or_later(loaded):
    _, contexts, by_id = loaded
    linked = [c for c in contexts if "last_order" in c]

    assert linked and all(by_id[c["last_order"]]["month"] < c["month"] for c in linked)
    assert all(by_id[c["last_order"]]["customer_id"] == c["customer"] for c in linked)


def test_the_link_agrees_with_the_denormalised_previous_basket_the_fixtures_already_carry(loaded):
    _, contexts, by_id = loaded
    with_both = [c for c in contexts if "last_order" in c and c.get("prev_basket")]

    assert with_both
    assert all(set(by_id[c["last_order"]]["skus"].split()) == set(c["prev_basket"].split()) for c in with_both)
    assert len(with_both) == sum(1 for c in contexts if c.get("prev_basket"))      # same contexts have both
