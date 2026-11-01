"""The words of feedback (ADR 0058): reviews that read like their stars, NPS comments that follow the order's causes, a ground truth for each."""

import random
import re

import pytest

from data import feedback_text as ft

POSITIVE = re.compile(r"loves|best we have tried|great|just what we needed|five stars|approves|good quality|fresh|perfectly|arrived quickly|cannot get enough", re.I)
COMPLAINT = re.compile(r"poor|off and|refused|worse|damaged|too long|crushed|wrong size|does not fit|returned it|far off|\bill\b|sick|wrong|bad batch|disappointed", re.I)
RATINGS = {"praise": (4, 5), "quality": (1, 2, 3, 4), "shipping": (1, 2, 3), "fit": (1, 2, 3, 4), "question": (1, 2, 3, 4, 5)}   # the stars each topic gets in the fixtures


def texts(category: str, rating: int, n: int = 200, **kw) -> list[str]:
    rng = random.Random(f"{category}{rating}")
    return [ft.review_text(rng, category, rating, "Salmon kibble 2kg", "dog", **kw) for _ in range(n)]


@pytest.mark.parametrize("category, ratings", RATINGS.items())
def test_every_review_names_its_product_and_has_text_for_every_star_it_gets(category, ratings):
    for rating in ratings:
        assert all("Salmon kibble 2kg" in t for t in texts(category, rating)), (category, rating)


@pytest.mark.parametrize("category, ratings", RATINGS.items())
def test_a_review_of_one_or_two_stars_does_not_read_as_praise(category, ratings):
    for rating in (r for r in ratings if r <= 2):
        assert not any(POSITIVE.search(t) for t in texts(category, rating)), (category, rating)


@pytest.mark.parametrize("category, ratings", RATINGS.items())
def test_a_review_of_four_or_five_stars_does_not_read_as_a_complaint(category, ratings):
    for rating in (r for r in ratings if r >= 4):
        assert not any(COMPLAINT.search(t) for t in texts(category, rating)), (category, rating)


def test_a_bad_unit_from_the_recalled_batch_says_the_animal_got_ill_and_never_mentions_death():
    recalled = texts("quality", 1, incident="recalled")

    assert all(re.search(r"ill|sick", t) for t in recalled)
    everything = " ".join(ft.RECALLED_REVIEW + [ft.RECALLED_CLAUSE] + [c for tone in ft.REVIEW_CLAUSES.values() for pool in tone.values() for c in pool])
    assert not re.search(r"\b(died|dead|death|die|killed)\b", everything, re.I)


def test_a_quiet_incident_says_what_was_wrong_and_that_the_customer_switched():
    assert all("switched" in t or "trust" in t for t in texts("quality", 1, incident="quiet"))


def comments(group="detractor", experience="bad", n=400, **kw):
    rng = random.Random(f"{group}{experience}")
    return [ft.nps_comment(rng, group, experience, "Salmon kibble 2kg", "dog", kw.get("delivery_problem", False), kw.get("returned", False), kw.get("incident"))
            for _ in range(n)]


def test_about_half_of_promoters_and_detractors_and_a_quarter_of_passives_comment():
    for group, expected in ft.COMMENT_P.items():
        share = sum(c is not None for c, _ in comments(group, "ok")) / 400
        assert abs(share - expected) < 0.08, group


def test_a_comment_that_says_it_names_the_product_does_and_the_topics_are_what_it_talks_about():
    for text, truth in (c for c in comments("detractor", "bad", delivery_problem=True, returned=True) if c[0]):
        assert ("Salmon kibble 2kg" in text) == truth["names_product"]
        assert {"delivery", "returns"} <= set(truth["topics"]), text
        assert "delivery" in text.lower() or "parcel" in text.lower()


def test_a_comment_can_name_a_product_and_a_second_topic():
    both = [truth for text, truth in comments("passive", "ok", delivery_problem=True, n=800) if text and truth["names_product"] and "delivery" in truth["topics"]]

    assert both


def test_a_recalled_bad_unit_is_described_as_making_the_animal_ill_in_the_comment():
    found = [t for t, truth in comments("detractor", "bad", incident="recalled") if t]

    assert found and all("ill" in t for t in found) and all("health" in truth["topics"] for _, truth in comments("detractor", "bad", incident="recalled") if _)


def test_no_text_names_a_real_retailer_brand_or_event():
    pools = " ".join([*ft.RECALLED_REVIEW, *ft.QUIET_REVIEW, ft.RECALLED_CLAUSE, ft.QUIET_CLAUSE] + [c for tone in ft.REVIEW_CLAUSES.values() for pool in tone.values() for c in pool])

    assert not re.search(r"Musti|Mirri|SMAAK|Yle|Lieto|Royal Canin|Acana|Hill", pools)
