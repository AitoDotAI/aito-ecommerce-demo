"""The Shop's `where`: who is shopping, when, what is in their cart and
what their household owns, as the contexts table records them (ADR 0033),
and their declared diet as a filter (ADR 0031).
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


def shopper_where(customer_id: str, cart: list[dict], month: str, owned: list[str]) -> dict:
    """Who is shopping, the month, the cart and the kit they own, as `_recommend`
    context. Only what a shop observes: Aito learns the customer from their
    own rows (`context.customer`), never from a profile handed to it."""
    where: dict = {"context.customer": customer_id, "context.month": month}
    if cart:
        where["context.basket_categories"] = {"$and": [{"$match": w} for w in basket_words(cart)]}
        where["context.basket"] = {"$and": [{"$match": p["sku"]} for p in cart]}
    if owned:
        where["context.owned"] = {"$and": [{"$match": t} for t in owned]}
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
