"""Shoppers with a story: the rules behind ADR 0030's planted effects.

`generate_fixtures.py` applies them; `tests/test_shoppers_data.py` checks
the result against the thresholds in
`docs/verification/shoppers-data-prereg.md`.

- **Diet rules (S1).** Some dog and cat households only ever buy one kind
  of food: grain-free, sensitive stomach, senior, or puppy.
- **Guided kit (S2).** Add-ons follow the kit in order.
- **Seasons (S4).** Treats and toys before Christmas, grooming and health
  care in summer.
- **Ratings matter (S5).** Some products are poorly made: they review
  badly, get switched away from, and convert less.
- **Basket context (S6).** What's in the basket makes its complements
  more likely to be bought.
- **Real search queries (S7).** Words from the products' own names.
"""

from __future__ import annotations

import hashlib
import random

from data import lifecycle

FOOD = frozenset({"dry-food", "wet-food"})

# ── S1: diet rules ──────────────────────────────────────────────────

DIET_RULE_P = 0.20
# The words a product's name carries when it keeps the rule.
RULE_WORDS = {"grain-free": "Grain Free", "sensitive": "Sensitive", "senior": "Senior", "puppy": "Puppy"}


def assign_diet_rule(rng: random.Random, pets: list[str]) -> str | None:
    """A rule for a dog or cat household, or None. Puppy food exists only
    for dogs, so `puppy` goes only to households without a cat."""
    if not {"dog", "cat"} & set(pets) or rng.random() >= DIET_RULE_P:
        return None
    options = ["grain-free", "sensitive", "senior"] + (["puppy"] if "cat" not in pets else [])
    return rng.choice(options)


def keeps_diet_rule(name: str, pet_type: str, category: str, rule: str | None) -> bool:
    """The rule covers dog and cat food only; anything else keeps it."""
    if rule is None or pet_type not in ("dog", "cat") or category not in FOOD:
        return True
    return RULE_WORDS[rule] in name


# ── S2: the kit's add-ons, in order ─────────────────────────────────

NEXT_ADD_ON_P = 0.90
OUT_OF_ORDER_SKIP_P = 0.80      # a random basket draw of a later add-on is mostly skipped


def out_of_order(pet: str, kind: str, owned: set[str]) -> bool:
    """`kind` is one of the pet's add-ons, not yet owned, and not the next one."""
    sequence = lifecycle.ADD_ONS.get(pet, ())
    wanted = [k for k in sequence if k not in owned]
    return kind in wanted and kind != wanted[0]


def next_add_on(rng: random.Random, sequence: tuple[str, ...], owned: set[str]) -> str | None:
    """The next unowned add-on in the kit's order, or (1 − NEXT_ADD_ON_P)
    of the time another unowned one."""
    wanted = [kind for kind in sequence if kind not in owned]
    if not wanted:
        return None
    return wanted[0] if rng.random() < NEXT_ADD_ON_P else rng.choice(wanted)


# ── S4: seasons ─────────────────────────────────────────────────────

SEASON_FACTORS: dict[int, dict[str, float]] = {
    11: {"treats": 1.4, "toys": 1.4},
    12: {"treats": 2.0, "toys": 2.0},
    6: {"grooming": 1.7, "health": 1.7},
    7: {"grooming": 1.7, "health": 1.7},
    8: {"grooming": 1.7, "health": 1.7},
}
# A gift line added to an order in these months, and a summer care line
# (pre-registration amendments): staples fill most lines, so a pick weight
# alone barely moves a category's share.
GIFT_LINE_P = {11: 0.15, 12: 0.35}
GIFT_CATEGORIES = ("treats", "toys")
CARE_LINE_P = {6: 0.25, 7: 0.25, 8: 0.25}
CARE_CATEGORIES = ("grooming", "health")


def season_factor(category: str, month: str) -> float:
    """How much more often `category` is picked in `month` ("2025-12")."""
    return SEASON_FACTORS.get(int(month[5:]), {}).get(category, 1.0)


# ── S5: poorly made products ────────────────────────────────────────

POOR_SHARE = 0.15
POOR_SWITCH_P = 0.50            # a poorly made staple is switched away from this often
POOR_CONVERSION_ODDS = 0.35     # an impression of one converts at these odds
RATING_WEIGHTS = {
    True:  {1: 0.35, 2: 0.30, 3: 0.20, 4: 0.10, 5: 0.05},
    False: {1: 0.05, 2: 0.10, 3: 0.20, 4: 0.30, 5: 0.35},
}


def is_poorly_made(sku: str) -> bool:
    """Fixed per SKU from a hash, not the RNG, so tests can name the same
    products without re-running the generator."""
    return int(hashlib.md5(sku.encode()).hexdigest(), 16) % 100 < POOR_SHARE * 100


def rating_band(avg_rating: float | None) -> str:
    if avg_rating is None:
        return "unrated"
    if avg_rating < 2.5:
        return "1-2"
    if avg_rating < 3.5:
        return "3"
    return "4" if avg_rating < 4.5 else "5"


# ── S6: basket context ──────────────────────────────────────────────

COMPLEMENT_ODDS = 3.0           # on the click, the add-to-cart and the purchase


def _token(pet: str, word: str) -> str:
    # Aito's Text analyzers split on hyphens and spaces, so a token keeps
    # neither: "dog_dryfood", "small_animal_water_bottle" (as
    # orders.line_categories does).
    return f"{pet}_{word.lower().replace('-', '').replace(' ', '_')}"


def basket_tokens(products: list) -> list[str]:
    """Words for a basket: `dog_dryfood` per line, and `small_animal_cage`
    for each durable kit item, so a Text column can `$match` either."""
    tokens: list[str] = []
    for p in products:
        tokens.append(_token(p.pet_type, p.category))
        kind = lifecycle.item_type(p.name, p.brand)
        if kind in lifecycle.DURABLE_TYPES:
            tokens.append(_token(p.pet_type, kind))
    return sorted(set(tokens))


def complements_basket(product: dict, basket: list[str]) -> bool:
    """An add-on of a kit item in the basket, or dental treats with dog dry
    food. `product` is a products.json row."""
    pet = product["pet_type"]
    kind = lifecycle.item_type(product["name"], product["brand"])
    if kind in lifecycle.ADD_ONS.get(pet, ()):
        kit = lifecycle.STARTER_KITS.get(pet, ())
        return any(_token(pet, k) in basket for k in kit)
    return pet == "dog" and product["category"] == "dental-treats" and "dog_dryfood" in basket


# ── S7: search queries from the products' own words ─────────────────

MIN_QUERY_MATCHES = 3


def query_phrases(products: list) -> dict[str, list]:
    """Every 2–3 word phrase from a product's type (its name without brand
    or size) that at least MIN_QUERY_MATCHES product names contain,
    mapped to those products."""
    names = [(p, p.name.lower()) for p in products]
    phrases: dict[str, list] = {}
    for p in products:
        words = lifecycle.item_type(p.name, p.brand).lower().split()
        for n in (2, 3):
            for start in range(len(words) - n + 1):
                phrase = " ".join(words[start:start + n])
                if phrase in phrases:
                    continue
                matching = [q for q, name in names if all(w in name.split() for w in phrase.split())]
                if len(matching) >= MIN_QUERY_MATCHES:
                    phrases[phrase] = matching
    return phrases
