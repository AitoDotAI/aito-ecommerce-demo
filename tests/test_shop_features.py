"""The tokens behind a card's "products with this one's features" term (src/shop_features.py)."""

from src.shop_features import product_features

PRODUCT = {"name": "Trixie Hideout, small", "tags": "mass everyday outdoor", "brand": "Trixie",
           "category": "accessories", "pet_type": "small_animal"}
STATE = {"discount_band": "none", "rating_band": "3", "age": "established", "label": "recommended",
         "stock": "in_stock", "review_count_band": "1-4", "price_change": "none",
         "rival_launched": False, "on_offer": False}


def _tokens(features):
    return {f.field: f.tokens for f in features}


def test_text_columns_are_split_into_the_words_their_analyzer_sees():
    tokens = _tokens(product_features(PRODUCT, STATE))

    assert tokens["Name"] == ["Trixie", "Hideout,", "small"]    # the comma stays: it is the token
    assert tokens["Tags"] == ["mass", "everyday", "outdoor"]


def test_product_and_state_columns_are_single_values():
    tokens = _tokens(product_features(PRODUCT, STATE))

    assert tokens["Brand"] == ["Trixie"] and tokens["Category"] == ["accessories"]
    assert tokens["Offer"] == ["none"] and tokens["Stars"] == ["3"] and tokens["On offer"] == ["false"]


def test_a_product_without_a_state_this_month_lists_only_its_own_columns():
    tokens = _tokens(product_features(PRODUCT, None))

    assert "Brand" in tokens and "Offer" not in tokens


def test_a_text_column_with_no_value_is_left_out():
    assert "Tags" not in _tokens(product_features({**PRODUCT, "tags": None}, STATE))
