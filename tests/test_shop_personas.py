"""Each Shop persona's story is true of the generated data (ADR 0031).

The stories are what a demo viewer reads, so they're checked against the
fixtures like any other engineered signal.
"""

import json
from pathlib import Path

import pytest

from data import lifecycle
from tests.fixture_joins import customers_with_traits

from src.shop_personas import NO_CONSENT_SHOPPER, NO_PET_PROFILE_SHOPPER, SHOPPERS, UnknownShopperError, shopper

DATA = Path(__file__).resolve().parent.parent / "data"


def _load(name: str) -> list[dict]:
    return json.loads((DATA / name).read_text())


@pytest.fixture(scope="module")
def history():
    products = {p["sku"]: p for p in _load("products.json")}
    customers = {c["customer_id"]: c for c in customers_with_traits()}
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


def test_paivi_is_a_new_guinea_pig_owner_with_a_cage_and_a_bottle_by_april(history):
    products, _, orders = history
    paivi = orders[shopper("paivi").customer_id]
    before_april = [o for o in paivi if o["month"] < "2026-04"]
    kinds = {lifecycle.item_type(p["name"], p["brand"]) for p in _bought(products, before_april)}
    assert len(paivi) <= 3
    assert {"Cage", "Water Bottle"} <= kinds and "Hideout" not in kinds
    assert {p["pet_type"] for p in _bought(products, paivi)} == {"small_animal"}
    food = [p["name"] for p in _bought(products, paivi) if p["category"] == "dry-food"]
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


def test_every_shopper_but_one_consented_to_behavioural_tracking(history):
    _, customers, _ = history
    declined = [person.key for person in SHOPPERS if not customers[person.customer_id]["consent_behavioural"]]
    assert declined == [NO_CONSENT_SHOPPER]


def test_juhani_has_orders_and_declared_interests_but_no_visits(history):
    _, customers, orders = history
    juhani = shopper(NO_CONSENT_SHOPPER).customer_id
    assert len(orders[juhani]) == 8
    assert customers[juhani]["interests"].split() == ["grooming", "toys_and_play", "budget_buys"]
    assert not [c for c in _load("contexts.json") if c.get("customer") == juhani]


def test_olli_reorders_eukanuba(history):
    products, customers, orders = history
    olli = shopper("olli").customer_id
    assert customers[olli]["dog_size"] == "small"
    food = [p["name"] for p in _bought(products, orders[olli]) if p["category"] in ("dry-food", "wet-food")]
    assert max(set(food), key=food.count).startswith("Eukanuba")


def test_saara_buys_the_same_large_breed_bag_in_7_of_13_orders(history):
    products, _, orders = history
    saara = orders[shopper("saara").customer_id]
    bag = "Acana Weight Control Salmon Dog Food 7kg"
    assert len(saara) == 13
    assert sum(any(products[s]["name"] == bag for s in o["skus"].split()) for o in saara) == 7


def test_paivi_declared_her_pet_profile(history):
    _, customers, _ = history
    assert customers[shopper("paivi").customer_id]["pets"] == "small_animal"


def test_eemil_declared_no_pets_and_the_shop_reads_a_dog_from_his_orders(history):
    products, customers, orders = history
    eemil = shopper(NO_PET_PROFILE_SHOPPER).customer_id
    assert "pets" not in customers[eemil]
    assert len(orders[eemil]) == 13
    assert {p["pet_type"] for p in _bought(products, orders[eemil])} == {"dog"}
    later = [c for c in _load("contexts.json") if c.get("customer") == eemil and c.get("pets_from_orders")]
    assert later and all(c["pets_from_orders"] == "dog" for c in later)


def test_an_unknown_shopper_is_refused():
    with pytest.raises(UnknownShopperError, match="nobody"):
        shopper("nobody")
