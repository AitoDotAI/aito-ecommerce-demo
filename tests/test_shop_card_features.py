"""A card's features: one lift each, groups apart, the matched word marked (src/shop_card_features.py)."""

import pytest

from src.aito_client import AitoError
from src.shop_card_features import features_from

PRODUCT = {"name": "Trixie Hideout, small", "tags": "mass everyday outdoor"}


def _lift(value, **propositions):
    return {"type": "relatedPropositionLift", "proposition": propositions, "value": value}


def _hit(*factors):
    return {"$p": 0.27, "$why": {"type": "product", "factors": [
        {"type": "baseP", "value": 0.14, "proposition": {"purchased": True}}, *factors]}}


def test_features_are_sorted_by_how_far_they_move_the_odds_in_either_direction():
    hit = _hit(_lift(1.2, **{"product_state.label": "recommended"}),
               _lift(0.5, **{"product_state.discount_band": "none"}),
               _lift(1.6, **{"product_sku.brand": "Trixie"}))

    got = features_from(hit, "SKU", PRODUCT)

    assert [p.features[0].label for p in got.patterns] == ["Offer: none", "Brand is Trixie", "Label: recommended"]


def test_a_text_feature_shows_the_field_with_the_matched_word_marked():
    hit = _hit(_lift(1.5, **{"product_sku.name": {"$match": "Hideout,"}}))

    [pattern] = features_from(hit, "SKU", PRODUCT).patterns

    assert pattern.features[0].label == "Name has the word Hideout,"
    assert pattern.features[0].marked_text == "Trixie «Hideout,» small"


def test_features_aito_estimated_as_a_group_are_listed_apart_with_one_lift():
    group = {"$and": [{"product_sku.brand": "Trixie"}, {"product_sku.category": "accessories"}]}
    hit = _hit(_lift(0.9, **{"$and": group["$and"]}), _lift(1.1, **{"product_sku.brand": "Trixie"}))

    got = features_from(hit, "SKU", PRODUCT)

    assert [p.lift for p in got.patterns] == [1.1]
    assert [(p.lift, [f.label for f in p.features]) for p in got.joint] == [
        (0.9, ["Brand is Trixie", "Category is accessories"])]


def test_the_situations_lifts_are_left_to_the_cards_chain():
    hit = _hit(_lift(2.0, **{"context.month": "2026-04"}), _lift(1.1, **{"product_sku.brand": "Trixie"}))

    assert [p.features[0].label for p in features_from(hit, "SKU", PRODUCT).patterns] == ["Brand is Trixie"]


def test_an_unknown_feature_fails_loudly():
    with pytest.raises(AitoError, match="product_state.mystery"):
        features_from(_hit(_lift(1.1, **{"product_state.mystery": "x"})), "SKU", PRODUCT)
