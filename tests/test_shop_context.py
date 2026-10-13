"""The Shop's `where` (src/shop_context.py): profile, month, cart and rule."""

from data import lifecycle
from src.shop_context import DURABLE_TYPES, basket_words, rule_filter, shopper_where

CAGE = {"sku": "SKU-PT-0530", "name": "Trixie Cage", "brand": "Trixie",
        "pet_type": "small_animal", "category": "accessories"}
FOOD = {"sku": "SKU-PT-0012", "name": "Acana Grain Free Lamb Dog Food 2kg", "brand": "Acana",
        "pet_type": "dog", "category": "dry-food"}
CUSTOMER = {"segment": "dog_owner", "lifestyle": "mid", "health_focus": "high",
            "treat_affinity": "low", "brand_loyalty": "loyal", "diet_rule": "grain-free"}


def test_durable_kit_items_match_the_generators():
    # The generator writes these into basket_categories; a cart must use the same words.
    assert DURABLE_TYPES == lifecycle.DURABLE_TYPES


def test_a_cart_is_described_with_the_words_impressions_record():
    assert basket_words([CAGE, FOOD]) == ["dog_dryfood", "small_animal_accessories", "small_animal_cage"]


def test_the_where_holds_profile_month_and_cart_but_not_the_rule():
    where = shopper_where(CUSTOMER, [CAGE], "2025-12")

    assert where["customer_segment"] == "dog_owner" and where["month"] == "2025-12"
    assert where["basket_skus"] == {"$and": [{"$match": "SKU-PT-0530"}]}
    assert {"$match": "small_animal_cage"} in where["basket_categories"]["$and"]
    assert "customer_diet_rule" not in where   # the rule is a filter, see rule_filter


def test_an_empty_cart_adds_no_basket_context():
    where = shopper_where(CUSTOMER, [], "2025-12")

    assert "basket_skus" not in where and "basket_categories" not in where


def test_a_rule_keeps_non_food_other_pets_food_and_food_that_names_it():
    # As the generator's rule: it covers dog and cat food only, so a
    # grain-free household's guinea-pig food stays on offer.
    assert rule_filter("grain-free") == {"$or": [
        {"product_sku.category": {"$not": {"$or": ["dry-food", "wet-food"]}}},
        {"product_sku.pet_type": {"$not": {"$or": ["dog", "cat"]}}},
        {"product_sku.name": {"$match": "Grain"}},
    ]}
    assert rule_filter(None) is None
