"""The Shop's `where` for "Picked for you": the household's declared pets,
the month and the cart, as the contexts table records them, and their
declared diet as a filter (ADR 0031, ADR 0033 and its amendment of
2026-10-21: one view per intent).
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


def shopper_where(pets: str, cart: list[dict], month: str) -> dict:
    """The household's declared pets, the month and the cart, as `_recommend`
    context. Not the customer's identity: on held-out sessions it made the
    probabilities worse (observable-data-prereg.md, R1/R2). Not the kit:
    "Next for their kit" has its own view, because adding the kit to the
    same query erased its lift (ADR 0033, amendment of 2026-10-21)."""
    where: dict = {"context.customer.pets": {"$and": [{"$match": p} for p in pets.split()]},
                   "context.month": month}
    if cart:
        # The cart as words, not SKUs: an exact SKU next to the owned kit makes a
        # joint condition no row matches, and Aito's estimate then collapses
        # (td-20261020210945109481). The SKUs still keep the cart's own items
        # out of the candidates (ShopScope.where).
        where["context.basket_categories"] = {"$and": [{"$match": w} for w in basket_words(cart)]}
    return where


def shopper_where_from_orders(pets: str, cart: list[dict], month: str) -> dict:
    """`shopper_where` for a household that declared no pet profile (most don't,
    ADR 0045): the pet types of its earlier orders, as `contexts.pets_from_orders`
    records them, in place of the declared pets. Identity-free, so it also serves
    a shopper who declined tracking, who has no contexts to match."""
    where = shopper_where(pets, cart, month)
    where["context.pets_from_orders"] = where.pop("context.customer.pets")
    return where


def pets_filter(pets: str) -> dict:
    """The household's declared pets as a filter on the candidates: a cat
    household is shown cat products. A rule, like the diet: Aito saw dog
    treats shown to cat households only 7 times, too few to learn that they
    never buy them (×0.89 against the treats' general ×3.1, 2026-10-21)."""
    return {"product_sku.pet_type": {"$or": pets.split()}}


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
