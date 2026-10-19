"""What a shop can observe, and the kit's next item (ADR 0033).

The generator keeps a hidden model of each customer (lifestyle, health
focus, treat affinity, brand loyalty, segment) that drives what they do.
None of it is written for Aito. What is written is what a shop has:

- `customers`: what the customer declared or the shop recorded
  (`public_customer`).
- `contexts`: one row per moment products were shown: who, when, where,
  the basket, the previous basket and what the household owns (`Context`).

K1, the kit's next item (docs/verification/observable-data-prereg.md):
a shown kit item converts by where the household is in its kit, read
from the basket and from what it owns (`kit_odds`).
"""

from __future__ import annotations

from dataclasses import dataclass

from data import lifecycle, shoppers

# The generator's hidden model: never a column in any table Aito sees.
HIDDEN_TRAITS = ("segment", "lifestyle", "health_focus", "treat_affinity", "brand_loyalty")

KIT_PROGRESSION = True      # K1 on; its null keeps ADR 0030's S6 kit rule instead
OWNED_KIT_ODDS = 0.1        # a kit item the household has: nobody needs a second cage
NEXT_KIT_ODDS = 5.0         # the kit's next missing item
OTHER_ADD_ON_ODDS = 1.5     # another add-on not yet owned


def public_customer(customer) -> dict:
    """The customers row: declared and recorded fields only."""
    row = {
        "customer_id": customer.customer_id,
        "name": customer.name,
        "region": customer.region,
        "tenure_months": customer.tenure_months,
        "pets": " ".join(customer.pets),
        "dog_size": customer.pet_size if "dog" in customer.pets else None,
        "diet": customer.diet_rule,
        "total_orders": customer.total_orders,
        "total_spent_eur": customer.total_spent_eur,
        "last_order_month": customer.last_order_month,
        "churned": customer.churned,
    }
    return {k: v for k, v in row.items() if v is not None}


def answer_key_row(customer) -> dict:
    """The hidden model of one customer, for the data checks only. Written to
    `data/answer_key/`, which the loader never uploads (it loads the tables
    of `src/schema.py`)."""
    row = {"customer_id": customer.customer_id, "pet_size": customer.pet_size,
           "diet_rule": customer.diet_rule, "pets": " ".join(customer.pets)}
    row.update({trait: getattr(customer, trait) for trait in HIDDEN_TRAITS})
    return {k: v for k, v in row.items() if v is not None}


@dataclass
class Context:
    """One moment a customer was shown products (one session)."""
    context_id: str                 # "SESS-000001"
    customer: str                   # link → customers.customer_id
    month: str
    weekday: str
    surface: str                    # search | for_you | category | bought_together
    search_query: str | None = None
    basket: str | None = None              # this month's basket, SKUs
    basket_categories: str | None = None   # the same as words: "small_animal_cage dog_dryfood"
    prev_basket: str | None = None         # the last order before this month, SKUs
    owned: str | None = None               # kit items owned from earlier orders: "small_animal_cage"


def kit_sequence(pet: str) -> tuple[str, ...]:
    """The kit in the order a household completes it: starter kit, then add-ons."""
    return lifecycle.STARTER_KITS.get(pet, ()) + lifecycle.ADD_ONS.get(pet, ())


def kit_odds(product: dict, basket: set[str], owned: set[str]) -> float:
    """K1: how much the household's place in its kit moves this shown product.

    `product` is a products.json-style row; `basket` and `owned` are kit
    tokens ("small_animal_cage"). The kit counts as started when any of
    its items is in the basket or owned."""
    pet = product["pet_type"]
    kind = lifecycle.item_type(product["name"], product["brand"])
    sequence = kit_sequence(pet)
    if kind not in sequence:
        return 1.0
    have = {k for k in sequence if shoppers.token(pet, k) in basket | owned}
    if not have:
        return 1.0
    if kind in have:
        return OWNED_KIT_ODDS
    next_missing = next(k for k in sequence if k not in have)
    if kind == next_missing:
        return NEXT_KIT_ODDS
    return OTHER_ADD_ON_ODDS if kind in lifecycle.ADD_ONS.get(pet, ()) else 1.0
