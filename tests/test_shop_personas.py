"""Each Shop persona's story is true of the generated data (ADR 0031).

The stories are what a demo viewer reads, so they're checked against the
fixtures like any other engineered signal.
"""

import json
from pathlib import Path

import pytest

from data import lifecycle

from src.shop_personas import SHOPPERS, UnknownShopperError, shopper

DATA = Path(__file__).resolve().parent.parent / "data"


def _load(name: str) -> list[dict]:
    return json.loads((DATA / name).read_text())


@pytest.fixture(scope="module")
def history():
    products = {p["sku"]: p for p in _load("products.json")}
    customers = {c["customer_id"]: c for c in _load("customers.json")}
    orders: dict[str, list[dict]] = {}
    for o in sorted(_load("orders.json"), key=lambda o: o["month"]):
        orders.setdefault(o["customer_id"], []).append(o)
    return products, customers, orders


def _bought(products, orders) -> list[dict]:
    return [products[s] for o in orders for s in o["skus"].split()]


def test_every_shopper_is_an_active_customer(history):
    _, customers, orders = history
    for s in SHOPPERS:
        assert s.customer_id in customers, s
        assert not customers[s.customer_id]["churned"], s
        assert orders.get(s.customer_id), s


def test_sofia_is_a_new_guinea_pig_owner_with_a_cage_bottle_and_hideout(history):
    products, _, orders = history
    sofia = orders[shopper("sofia").customer_id]
    kinds = {lifecycle.item_type(p["name"], p["brand"]) for p in _bought(products, sofia)}
    assert len(sofia) <= 3
    assert {"Cage", "Water Bottle", "Hideout"} <= kinds
    assert {p["pet_type"] for p in _bought(products, sofia)} == {"small_animal"}
    food = [p["name"] for p in _bought(products, sofia) if p["category"] == "dry-food"]
    assert food and all("Guinea Pig" in name for name in food)


def test_janne_only_ever_buys_grain_free_food(history):
    products, customers, orders = history
    janne = shopper("janne").customer_id
    assert customers[janne]["diet_rule"] == "grain-free"
    food = [p for p in _bought(products, orders[janne]) if p["category"] in ("dry-food", "wet-food")]
    assert food and all("Grain Free" in p["name"] for p in food)


def test_helena_rebuys_the_same_cat_food(history):
    products, _, orders = history
    helena = orders[shopper("helena").customer_id]
    food = [p["sku"] for p in _bought(products, helena) if p["category"] in ("dry-food", "wet-food")]
    assert len(helena) >= 12
    assert max(food.count(s) for s in set(food)) >= 6


def test_an_unknown_shopper_is_refused():
    with pytest.raises(UnknownShopperError, match="nobody"):
        shopper("nobody")
