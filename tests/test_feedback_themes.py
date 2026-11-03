"""Theme tags are assigned from the words of a message, and a message no rule covers is refused."""
import json
from pathlib import Path

import pytest

from src.feedback_themes import themes_of

DATA = Path(__file__).resolve().parent.parent / "data"


def test_a_late_damaged_delivery_is_tagged_with_both_themes():
    assert themes_of("The Acana Large Breed Adult arrived late and the box was damaged.") == ["late-delivery", "damaged-packaging"]


def test_one_message_can_carry_a_complaint_and_what_the_customer_did_about_it():
    comment = "I was disappointed with the Kong Ball: the quality is not what I expected. I had to send one item back."

    assert themes_of(comment) == ["quality-below-expectations", "return-or-refund"]


def test_a_poor_review_that_asks_if_the_product_suits_a_pet_is_the_pet_rejecting_it_not_a_request_for_more():
    assert themes_of("Is the Kong Ball really suitable for a dog? Mine did not take to it.") == ["pet-rejected-it"]


def test_no_message_has_a_theme_if_there_is_no_message():
    assert themes_of(None) == [] and themes_of("") == []


def test_a_message_no_rule_covers_is_refused_not_left_untagged():
    with pytest.raises(ValueError, match="No theme rule covers"):
        themes_of("Totally unrelated words.")


def test_every_review_and_every_nps_comment_in_the_fixtures_gets_a_theme():
    reviews = json.loads((DATA / "reviews.json").read_text())
    comments = [a["comment"] for a in json.loads((DATA / "nps_responses.json").read_text()) if a.get("comment")]

    untagged = [t for t in [r["text"] for r in reviews] + comments if not themes_of(t)]

    assert untagged == []
