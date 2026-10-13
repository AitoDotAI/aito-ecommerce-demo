"""A customer's life with their pet, and prices set independently of demand.

ADR 0027. The first generator drew every order line independently, so a
customer's history couldn't predict their next basket: 6.7 % of food lines
re-bought a previous food, first and later orders had the same mix, and
customers bought second cages. It also set each month's price *from* that
month's demand, so a cheap month was a busy month by construction.

This module holds the rules that replace both:

- **Staples** (food, cat litter, fish food) are restocked order after order,
  with an occasional switch.
- **A starter kit** comes first for each of the customer's pets (a hamster
  owner: cage, water bottle, food). **Add-ons** implied by the kit follow in
  later orders.
- **Durables** (cages, bowls, collars…) are bought once, with a rare
  replacement.
- **Promotions** are decided first, per SKU and month, with a frequency that
  depends on the category. Demand then responds: a promoted SKU is picked
  (price / list)^ε times as often, with ε per SKU in [−2, −1]. A few SKUs are
  deliberately mispriced: list price above their category's level, and
  promoted most months.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

# Item types (a product's name without brand and size) bought once.
DURABLE_TYPES = frozenset({
    "Cage", "Cage Cover", "Water Bottle", "Hideout", "Exercise Wheel", "Tunnel",
    "Perch", "Feeder", "Swing", "Mirror", "Bell Toy",
    "Bowl", "Carrier", "Travel Carrier", "Scratching Post", "Water Fountain",
    "Collar", "Harness", "Leash", "Laser Pointer", "Nail Clipper", "Brush",
    "Air Pump", "Tank Heater",
})
REPLACEMENT_P = 0.02            # a durable bought again anyway (it broke)

# What a new owner buys first, besides their staple food.
STARTER_KITS: dict[str, tuple[str, ...]] = {
    "small_animal": ("Cage", "Water Bottle"),
    "bird":         ("Perch", "Feeder"),
    "cat":          ("Bowl",),
    "dog":          ("Bowl", "Collar"),
    "aquarium":     ("Air Pump", "Tank Heater"),
}

# What the kit leads to, in later orders.
ADD_ONS: dict[str, tuple[str, ...]] = {
    "small_animal": ("Hideout", "Exercise Wheel", "Tunnel"),
    "bird":         ("Swing", "Mirror", "Bell Toy", "Cage Cover"),
    "cat":          ("Scratching Post", "Carrier", "Water Fountain"),
    "dog":          ("Harness", "Leash"),
    "aquarium":     ("Filter Pads", "Aquatic Plants", "Water Conditioner"),
}
ADD_ON_P = 0.35                 # chance an order adds one not-yet-owned add-on

# Consumables a customer settles on and restocks. A dog's staple food is
# dry or wet, chosen once per customer (see `staple_categories`).
STAPLE_CATEGORIES: dict[str, tuple[str, ...]] = {
    "dog":          ("dry-food",),
    "cat":          ("dry-food", "wet-food", "litter"),
    "small_animal": ("dry-food",),
    "bird":         ("dry-food",),
    "aquarium":     ("aquarium",),     # flakes / pellets (see STAPLE_TYPES)
}
STAPLE_TYPES_AQUARIUM = frozenset({"Tropical Flakes", "Cichlid Pellets", "Algae Wafers"})
# Each staple, each later order. Not every basket holds food: owners also
# order treats and toys between restocks. (At 0.8, dog dry food sat in 54 %
# of all orders, which capped the engineered dry-food → dental lift at 1.8×,
# below the 2.5× the Bought Together moment needs.)
RESTOCK_P = 0.60
SWITCH_P = 0.07                 # a restock that switches to another product
STAPLE_LOYALTY = 0.85           # a food drawn in a staple's category is the staple

MAIN_PET_WEIGHT = 0.4           # a pet whose weight in the segment is at least this

# Promotions: how often a category is on offer, and how deep.
PROMO_P_BY_CATEGORY: dict[str, float] = {
    "treats": 0.30, "dental-treats": 0.30, "toys": 0.30,
    "dry-food": 0.12, "wet-food": 0.15, "litter": 0.12,
}
PROMO_P_DEFAULT = 0.18
PROMO_DEPTH = (0.10, 0.25)
ELASTICITY_RANGE = (-2.0, -1.0)
N_MISPRICED = 15
# Planted where products sell most months, so each has the ≥ 12 monthly
# observations the Price view needs before it may call an outlier.
MISPRICED_CATEGORIES = frozenset({"dry-food", "wet-food", "treats", "litter"})
MISPRICING_MARKUP = (1.15, 1.25)
MISPRICED_PROMO_P = 0.80


def item_type(name: str, brand: str) -> str:
    """"Trixie Cage" → "Cage"; "PetNord Water Bottle 500ml" → "Water Bottle"."""
    rest = name[len(brand):].strip() if name.startswith(brand) else name
    words = rest.split()
    if words and any(ch.isdigit() for ch in words[-1]):
        words = words[:-1]
    return " ".join(words)


def main_pets(pet_weights: dict[str, float]) -> list[str]:
    """The pets a customer actually keeps (weight ≥ MAIN_PET_WEIGHT), largest first."""
    pets = sorted((p for p, w in pet_weights.items() if w >= MAIN_PET_WEIGHT),
                  key=lambda p: -pet_weights[p])
    return pets or [max(pet_weights, key=pet_weights.get)]


# The rest of dog owners feed wet food. It also keeps dog dry food out of
# most baskets: the engineered dry-food → dental lift can't exceed
# 1 / P(dry food in an order), and at 0.65 it sat exactly on its 2.5x floor.
DOG_DRY_FOOD_SHARE = 0.55


def staple_categories(rng: random.Random, pet: str) -> tuple[str, ...]:
    """The categories this customer restocks for `pet`, chosen once."""
    if pet == "dog":
        return ("dry-food",) if rng.random() < DOG_DRY_FOOD_SHARE else ("wet-food",)
    return STAPLE_CATEGORIES.get(pet, ())


def is_staple(product, pet: str) -> bool:
    if product.pet_type != pet:
        return False
    if pet == "aquarium":
        return item_type(product.name, product.brand) in STAPLE_TYPES_AQUARIUM
    return True


@dataclass
class Promotions:
    """Decided before any order, independent of demand."""
    discount: dict[tuple[str, str], float]   # (sku, month) → 0 or 0.10-0.25
    elasticity: dict[str, float]             # sku → ε in [−2, −1]
    mispriced: frozenset[str]

    def demand_factor(self, sku: str, month: str) -> float:
        """How much more often a SKU is picked this month: (price / list)^ε."""
        d = self.discount.get((sku, month), 0.0)
        return (1.0 - d) ** self.elasticity[sku] if d else 1.0


def plan_promotions(rng: random.Random, products: list, months: list[str]) -> Promotions:
    """Pick the mispriced SKUs (raising their list price in place), then draw a
    promotion calendar and a price sensitivity for every SKU."""
    regular = sorted((p for p in products if p.category in MISPRICED_CATEGORIES), key=lambda p: p.sku)
    mispriced = frozenset(p.sku for p in rng.sample(regular, N_MISPRICED))
    for p in products:
        if p.sku in mispriced:
            p.price_eur = round(p.price_eur * rng.uniform(*MISPRICING_MARKUP), 2)
    discount: dict[tuple[str, str], float] = {}
    elasticity: dict[str, float] = {}
    for p in products:
        elasticity[p.sku] = rng.uniform(*ELASTICITY_RANGE)
        promo_p = MISPRICED_PROMO_P if p.sku in mispriced else PROMO_P_BY_CATEGORY.get(p.category, PROMO_P_DEFAULT)
        for m in months:
            if rng.random() < promo_p:
                discount[(p.sku, m)] = rng.uniform(*PROMO_DEPTH)
    return Promotions(discount=discount, elasticity=elasticity, mispriced=mispriced)
