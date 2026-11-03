"""A pattern from the Feedback tab's lists selects the reviews and NPS answers that have it."""
import pytest

from src.feedback_pattern_filter import answer_has, review_has

REVIEW = {"product_sku": "SKU-PT-0202", "category": "shipping", "created_at": "2025-10", "rating": 1, "text": "It arrived late and damaged."}
ANSWER = {"product_state": "SKU-PT-0086-2025-03", "month": "2025-03", "nps_group": "detractor", "comment": "I was disappointed with the quality."}


def spec(group, *clauses):
    return {"group": group, "clauses": list(clauses)}


def test_a_review_has_a_product_and_a_topic_when_both_clauses_hold():
    assert review_has(spec("stars", {"field": "product_sku", "value": "SKU-PT-0202"}, {"field": "category", "value": "shipping"}), REVIEW)
    assert not review_has(spec("stars", {"field": "product_sku", "value": "SKU-PT-0202"}, {"field": "category", "value": "quality"}), REVIEW)


def test_a_review_has_a_word_as_aito_counts_it_a_space_separated_token_with_its_punctuation():
    """Aito's text index splits on spaces: "damaged." is one word and "damaged" another, so the rows behind a word match the count Aito gave."""
    assert review_has(spec("stars", {"field": "text", "word": "late"}), REVIEW)
    assert review_has(spec("stars", {"field": "text", "word": "damaged."}), REVIEW)
    assert not review_has(spec("stars", {"field": "text", "word": "damaged"}), REVIEW)
    assert not review_has(spec("stars", {"field": "text", "word": "dam"}), REVIEW)


def test_a_review_of_three_stars_is_not_in_the_poor_reviews_group():
    assert not review_has(spec("stars", {"field": "text", "word": "late"}), {**REVIEW, "rating": 3})


def test_an_answer_has_the_product_its_order_was_about_and_a_word_of_the_comment():
    assert answer_has(spec("detractors", {"field": "product_state.product_sku", "value": "SKU-PT-0086"}, {"field": "comment", "word": "disappointed"}), ANSWER)
    assert not answer_has(spec("detractors", {"field": "comment", "word": "excellent"}), ANSWER)


def test_a_pattern_for_the_other_tab_is_refused_not_matched():
    with pytest.raises(ValueError, match="A pattern for this tab"):
        review_has(spec("detractors"), REVIEW)


def test_an_unknown_product_field_is_refused_not_matched():
    with pytest.raises(ValueError, match="Cannot filter by the product field"):
        review_has(spec("stars", {"field": "product_sku.colour", "value": "red"}), REVIEW)


def test_a_product_name_word_is_a_word_without_its_punctuation_as_aitos_default_analyzer_has_it():
    assert review_has(spec("stars", {"field": "product_sku.brand", "value": "PetNord"}, {"field": "product_sku.name", "word": "Bowl"}), {**REVIEW, "product_sku": _bowl_sku()})


def _bowl_sku():
    from src.feedback_pattern_filter import _products
    return next(sku for sku, p in _products().items() if "Bowl," in p["name"] and p["brand"] == "PetNord")


def test_a_review_and_an_answer_have_the_theme_tags_of_their_message():
    late = {"field": "themes", "word": "late-delivery"}

    assert review_has(spec("stars", late, {"field": "themes", "word": "damaged-packaging"}), {**REVIEW, "text": "The Kong Ball arrived late and the box was damaged."})
    assert not review_has(spec("stars", late), {**REVIEW, "text": "Packaging of the Kong Ball was crushed when it came."})
    assert answer_has(spec("detractors", {"field": "themes", "word": "losing-trust"}), {**ANSWER, "comment": "I will think twice before ordering again."})
    assert not answer_has(spec("detractors", {"field": "themes", "word": "losing-trust"}), {**ANSWER, "comment": None})
