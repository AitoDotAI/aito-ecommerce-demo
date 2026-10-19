"""The Shop's `where` (src/shop_context.py): customer, month, cart, kit and rule."""

from data import lifecycle
from src.shop_context import DURABLE_TYPES, basket_words, rule_filter, shopper_where

CAGE = {"sku": "SKU-PT-0530", "name": "Trixie Cage", "brand": "Trixie",
        "pet_type": "small_animal", "category": "accessories"}
FOOD = {"sku": "SKU-PT-0012", "name": "Acana Grain Free Lamb Dog Food 2kg", "brand": "Acana",
        "pet_type": "dog", "category": "dry-food"}


def test_durable_kit_items_match_the_generators():
    # The generator writes these into basket_categories; a cart must use the same words.
    assert DURABLE_TYPES == lifecycle.DURABLE_TYPES


def test_a_cart_is_described_with_the_words_impressions_record():
    assert basket_words([CAGE, FOOD]) == ["dog_dryfood", "small_animal_accessories", "small_animal_cage"]


def test_the_where_holds_only_what_a_shop_observes():
    where = shopper_where("CUST-00049", [CAGE], "2025-12", ["small_animal_water_bottle"])

    # ADR 0033: who, when, the cart and the kit, all through the context.
    assert where["context.customer"] == "CUST-00049" and where["context.month"] == "2025-12"
    assert where["context.basket"] == {"$and": [{"$match": "SKU-PT-0530"}]}
    assert {"$match": "small_animal_cage"} in where["context.basket_categories"]["$and"]
    assert where["context.owned"] == {"$and": [{"$match": "small_animal_water_bottle"}]}
    # No profile is handed over, and the diet rule is a filter (see rule_filter).
    assert all(key.startswith("context.") for key in where)


def test_an_empty_cart_and_no_kit_add_no_context_for_them():
    where = shopper_where("CUST-00049", [], "2025-12", [])

    assert set(where) == {"context.customer", "context.month"}


def test_a_rule_keeps_non_food_other_pets_food_and_food_that_names_it():
    # As the generator's rule: it covers dog and cat food only, so a
    # grain-free household's guinea-pig food stays on offer.
    assert rule_filter("grain-free") == {"$or": [
        {"product_sku.category": {"$not": {"$or": ["dry-food", "wet-food"]}}},
        {"product_sku.pet_type": {"$not": {"$or": ["dog", "cat"]}}},
        {"product_sku.name": {"$match": "Grain"}},
    ]}
    assert rule_filter(None) is None
