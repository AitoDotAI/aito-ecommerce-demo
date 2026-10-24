"""Category anchors for basket `_relate` queries over `orders.line_categories`.

`orders.line_categories` holds one token per (pet type, category) in the
order, written `<pet>_<category without hyphens>`: `dog_dryfood`,
`small_animal_toys`. The hyphens are stripped so Aito reads each pair as
one Text feature (ADR 0008).

This module names the anchors a picker offers and turns tokens back into
readable labels. Pattern Explorer and Product Insights use it.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AnchorOption:
    anchor_id: str    # token form, e.g. "dog_dryfood"
    pet_type: str
    category: str     # the original hyphenated form, e.g. "dry-food"
    display: str      # "Dog dry-food"


ANCHORS: list[AnchorOption] = [
    AnchorOption("dog_dryfood",      "dog",      "dry-food",      "Dog dry-food"),
    AnchorOption("cat_wetfood",      "cat",      "wet-food",      "Cat wet-food"),
    AnchorOption("cat_litter",       "cat",      "litter",        "Cat litter"),
    AnchorOption("dog_dentaltreats", "dog",      "dental-treats", "Dog dental treats"),
    AnchorOption("aquarium_aquarium", "aquarium", "aquarium",     "Aquarium food"),
    AnchorOption("dog_accessories",  "dog",      "accessories",   "Dog accessories"),
]

DEFAULT_ANCHOR = "dog_dryfood"


_TOKEN_TO_PAIR: dict[str, tuple[str, str]] = {
    a.anchor_id: (a.pet_type, a.category) for a in ANCHORS
}

# The category list of `data/generate_fixtures.py`, so this module doesn't
# import the whole generator.
_CLEAN_TO_HYPHENATED: dict[str, str] = {
    cat.replace("-", ""): cat
    for cat in (
        "dry-food", "wet-food", "treats", "dental-treats",
        "litter", "accessories", "health", "grooming",
        "toys", "aquarium",
    )
}


def token_to_pair(token: str) -> tuple[str, str] | None:
    """Decode `<pet>_<cleanedcategory>` → (pet_type, category_hyphenated).

    Splits on the LAST `_`, because compound pet types like
    `small_animal` contain underscores; the category side never does.
    """
    if token in _TOKEN_TO_PAIR:
        return _TOKEN_TO_PAIR[token]
    pet, _, clean_cat = token.rpartition("_")
    if not clean_cat:
        return None
    return pet, _CLEAN_TO_HYPHENATED.get(clean_cat, clean_cat)


def humanise(pet_type: str, category: str) -> str:
    """`("dog", "dry-food")` → `"Dog dry-food"`."""
    if pet_type == "aquarium" and category == "aquarium":
        return "Aquarium products"   # avoid "Aquarium aquarium"
    label_pet = "Aquarium" if pet_type == "aquarium" else pet_type.replace("_", " ").capitalize()
    return f"{label_pet} {category}"
