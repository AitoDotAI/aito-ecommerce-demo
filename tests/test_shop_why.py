"""The Shop card's ? popover reads a `_recommend` hit's `$why` as it is (src/shop_why.py)."""

import pytest

from src.aito_client import AitoError
from src.shop_why import shop_why

# A real hit's `$why`, probed 2026-10-25 on env release2 (Helena, April, one item in the cart).
PETS = {"$and": [{"context.pets_from_orders": {"$match": "cat"}}]}
CART = {"$and": [{"context.basket_categories": {"$match": "small_animal_accessories"}},
                 {"context.basket_categories": {"$match": "small_animal_hideout"}}]}
WHY = {"type": "product", "factors": [
    {"type": "baseP", "value": 0.1417, "proposition": {"purchased": True}},
    {"type": "relatedPropositionLift", "proposition": PETS, "value": 0.648},
    {"type": "relatedPropositionLift", "proposition": CART, "value": 0.910},
    {"type": "normalizer", "name": "context", "value": 0.995},
    {"type": "hitLinkPropositionLift", "proposition": {"product_sku": {"$has": "SKU-PT-0503"}}, "value": 1.115},
    {"type": "hitPropositionLift", "proposition": {"product_sku": {"$has": "SKU-PT-0503"}}, "value": 10.259,
     "factors": [
         {"type": "relatedPropositionLift", "proposition": {"just_bought": False}, "value": 0.997},
         {"type": "relatedPropositionLift", "proposition": PETS, "value": 3.525},
         {"type": "relatedPropositionLift", "proposition": {"context.month": "2026-04"}, "value": 2.2},
     ]},
    {"type": "normalizer", "name": "exclusiveness", "value": 0.538},
]}
CONTEXT = {"context.pets_from_orders": {"$match": "cat dog"}, "context.month": "2026-04",
           "context.basket_categories": CART}


def test_the_chain_has_the_base_the_situation_the_features_and_the_product_itself():
    payload = shop_why(WHY, 0.512, CONTEXT)

    assert payload["base_p"] == 0.1417 and payload["final_p"] == 0.512
    assert sorted(e["lift"] for e in payload["lifts"]) == [0.648, 0.91, 1.115, 10.259]


def test_the_biggest_effect_comes_first_whichever_way_it_points():
    payload = shop_why(WHY, 0.512, CONTEXT)

    # |log 10.259| > |log 0.648| (a drop to two thirds) > |log 1.115| > |log 0.91|
    assert [e["lift"] for e in payload["lifts"]] == [10.259, 0.648, 1.115, 0.91]


def test_the_products_own_lift_holds_the_single_conditions_that_make_it_up():
    own = next(e for e in shop_why(WHY, 0.512, CONTEXT)["lifts"] if "members" in e)

    assert [m["lift"] for m in own["members"]] == [3.525, 2.2, 0.997]
    assert sum("members" in e for e in shop_why(WHY, 0.512, CONTEXT)["lifts"]) == 1


def test_a_text_condition_shows_the_contexts_text_with_the_matched_word_marked():
    pets = next(e for e in shop_why(WHY, 0.512, CONTEXT)["lifts"] if e["lift"] == 0.648)

    assert pets["highlight"] == {"field": "pets_from_orders", "marked_text": "«cat» dog"}


def test_a_product_with_no_impressions_of_its_own_has_no_own_lift():
    without_own = {**WHY, "factors": [f for f in WHY["factors"] if f["type"] != "hitPropositionLift"]}

    assert [e["lift"] for e in shop_why(without_own, 0.3, CONTEXT)["lifts"]] == [0.648, 1.115, 0.91]


def test_an_unknown_term_fails_loudly_rather_than_dropping_out_of_the_chain():
    odd = {**WHY, "factors": WHY["factors"] + [{"type": "mystery", "value": 2.0}]}

    with pytest.raises(AitoError, match="mystery"):
        shop_why(odd, 0.5, CONTEXT)


def test_a_why_without_a_base_probability_fails_loudly():
    with pytest.raises(AitoError, match="baseP"):
        shop_why({"type": "product", "factors": []}, 0.5, CONTEXT)
