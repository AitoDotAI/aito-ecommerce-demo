"""The Shop's `where`: who the shopper is, their household rule, and their
cart, in the words the impressions table records (ADR 0030, 0031).
"""

from __future__ import annotations

FOOD = ["dry-food", "wet-food"]
# The word a product's name carries when it keeps a household's rule.
RULE_WORDS = {"grain-free": "Grain", "sensitive": "Sensitive", "senior": "Senior", "puppy": "Puppy"}
# Kit items bought once. Mirrors data/lifecycle.py's DURABLE_TYPES, which
# the generator writes into `basket_categories`; a test keeps them equal.
DURABLE_TYPES = frozenset({
    "Cage", "Cage Cover", "Water Bottle", "Hideout", "Exercise Wheel", "Tunnel",
    "Perch", "Feeder", "Swing", "Mirror", "Bell Toy",
    "Bowl", "Carrier", "Travel Carrier", "Scratching Post", "Water Fountain",
    "Collar", "Harness", "Leash", "Laser Pointer", "Nail Clipper", "Brush",
    "Air Pump", "Tank Heater",
})
PROFILE_FIELDS = ("segment", "lifestyle", "health_focus", "treat_affinity", "brand_loyalty")


def item_type(name: str, brand: str) -> str:
    """"PetNord Water Bottle 500ml" → "Water Bottle" (brand and size dropped)."""
    words = (name[len(brand):] if name.startswith(brand) else name).split()
    if words and any(ch.isdigit() for ch in words[-1]):
        words = words[:-1]
    return " ".join(words)


def basket_words(products: list[dict]) -> list[str]:
    """A cart as `basket_categories` tokens: `small_animal_accessories` per
    item and `small_animal_cage` per kit item. No hyphens or spaces: Aito's
    Text analyzers would split them."""
    words: set[str] = set()
    for p in products:
        words.add(f"{p['pet_type']}_{p['category'].replace('-', '')}")
        kind = item_type(p["name"], p["brand"])
        if kind in DURABLE_TYPES:
            words.add(f"{p['pet_type']}_{kind.lower().replace(' ', '_')}")
    return sorted(words)


def shopper_where(customer: dict, cart: list[dict], month: str) -> dict:
    """The shopper's profile, the month and the cart, as `_recommend` context."""
    where: dict = {f"customer_{k}": customer[k] for k in PROFILE_FIELDS}
    where["month"] = month
    if cart:
        where["basket_categories"] = {"$and": [{"$match": w} for w in basket_words(cart)]}
        where["basket_skus"] = {"$and": [{"$match": p["sku"]} for p in cart]}
    return where


def rule_filter(rule: str | None) -> dict | None:
    """A household rule as a filter on the candidates: anything that isn't
    dog or cat food, or food whose name carries the rule's word. A rule is a filter,
    not a prediction: 14 purchases can't teach it (ADR 0031, check A1)."""
    if rule is None:
        return None
    # As the generator's rule: dog and cat food only. A grain-free household's
    # guinea-pig food isn't covered by it.
    return {"$or": [
        {"product_sku.category": {"$not": {"$or": FOOD}}},
        {"product_sku.pet_type": {"$not": {"$or": ["dog", "cat"]}}},
        {"product_sku.name": {"$match": RULE_WORDS[rule]}},
    ]}
