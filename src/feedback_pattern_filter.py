"""Which reviews and NPS answers have a pattern from the Feedback tab's lists (`data/evidence/feedback-patterns.json`).

A pattern is a list of clauses, all of which a row must satisfy: a field with a value (`product_sku.brand` = "PetNord"), or a text field with a word
(`text` contains "damaged"). The group (reviews of 1–2 stars, NPS detractors) is one more condition. An unknown field raises: a pattern that cannot be
checked must not silently match everything or nothing.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from src.feedback_themes import themes_of

DATA = Path(__file__).resolve().parent.parent / "data"
# Aito splits `reviews.text` and `nps_responses.comment` on spaces ("damaged." and "damaged" are two words; schema analyzer "whitespace"),
# and a product's name with its default analyzer, which drops punctuation ("Bowl, medium" has the word "Bowl").
NAME_WORDS = re.compile(r"[A-Za-z][A-Za-z-]+")
PRODUCT_FIELDS = ("brand", "category", "pet_type")


@lru_cache(maxsize=1)
def _products() -> dict[str, dict]:
    return {p["sku"]: p for p in json.loads((DATA / "products.json").read_text())}


@lru_cache(maxsize=1)
def _rating_band() -> dict[str, str]:
    return {s["product_state_id"]: s["rating_band"] for s in json.loads((DATA / "product_states.json").read_text())}


def _product_attribute(sku: str, attribute: str):
    if attribute not in PRODUCT_FIELDS + ("name",):
        raise ValueError(f"Cannot filter by the product field {attribute!r}; it can be one of {', '.join(PRODUCT_FIELDS)}, name")
    return _products()[sku][attribute]


def review_field(review: dict, field: str):
    """The value of a pattern's field on a review: its own columns, or an attribute of its product."""
    if field == "themes":
        return " ".join(themes_of(review["text"]))
    if field in ("product_sku", "category", "created_at", "text", "rating"):
        return review[field]
    return _product_attribute(review["product_sku"], field.removeprefix("product_sku."))


def answer_field(answer: dict, field: str):
    sku = answer["product_state"].rsplit("-", 2)[0]
    if field == "product_state.product_sku":
        return sku
    if field == "product_state.rating_band":
        return _rating_band()[answer["product_state"]]
    if field == "comment":
        return answer.get("comment") or ""
    if field == "themes":
        return " ".join(themes_of(answer.get("comment")))
    if field == "month":
        return answer["month"]
    return _product_attribute(sku, field.removeprefix("product_state.product_sku."))


def _has_all(clauses: list[dict], field_of) -> bool:
    for clause in clauses:
        value = field_of(clause["field"])
        if "word" in clause:
            words = NAME_WORDS.findall(value) if clause["field"].endswith("name") else value.split()
            if clause["word"] not in words:
                return False
        elif value != clause["value"]:
            return False
    return True


def review_matches(clauses: list[dict], review: dict) -> bool:
    """Whether a review from `reviews.json` satisfies every clause, whatever its rating."""
    return _has_all(clauses, lambda field: review_field(review, field))


def answer_matches(clauses: list[dict], answer: dict) -> bool:
    """Whether an NPS answer from `nps_responses.json` satisfies every clause, whatever its group."""
    return _has_all(clauses, lambda field: answer_field(answer, field))


def review_has(spec: dict, review: dict) -> bool:
    """Whether a review from `reviews.json` is of 1–2 stars and has the pattern `spec` = {"group": "stars", "clauses": [...]}."""
    _check(spec, "stars")
    return review["rating"] <= 2 and review_matches(spec["clauses"], review)


def answer_has(spec: dict, answer: dict) -> bool:
    """Whether an NPS answer from `nps_responses.json` is a detractor's and has the pattern `spec` = {"group": "detractors", "clauses": [...]}."""
    _check(spec, "detractors")
    return answer["nps_group"] == "detractor" and answer_matches(spec["clauses"], answer)


def _check(spec: dict, group: str) -> None:
    if spec.get("group") != group or not isinstance(spec.get("clauses"), list):
        raise ValueError(f"A pattern for this tab is {{'group': {group!r}, 'clauses': [...]}}; got {spec!r}")
