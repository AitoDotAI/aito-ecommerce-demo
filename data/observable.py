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
# ADR 0038's sensitivities and ADR 0039's hidden causes, likewise.
SENSITIVITIES = ("discount", "stars", "newness", "labels")
HIDDEN_FIELDS = tuple(f"{s}_sensitivity" for s in SENSITIVITIES) + (
    "favorite_brands", "churn_month", "quality", "experience")

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
        # ADR 0040: the device it came from, and its first order.
        "visitor": customer.visitor,
        "first_source": customer.first_source,
        "joined_month": customer.joined_month,
        "first_basket_categories": customer.first_basket_categories,
        "became_regular": customer.became_regular,
        # ADR 0044: consent, the purchase form, the account, declared interests.
        "consent_behavioural": customer.consent_behavioural,
        "sex": customer.sex,
        "postcode_area": customer.postcode_area,
        "delivery_method": customer.delivery_method,
        "loyalty_member": customer.loyalty_member,
        "interests": customer.interests,
    }
    return {k: v for k, v in row.items() if v is not None}


def answer_key_row(customer) -> dict:
    """The hidden model of one customer, for the data checks only. Written to
    `data/answer_key/`, which the loader never uploads (it loads the tables
    of `src/schema.py`)."""
    row = {"customer_id": customer.customer_id, "pet_size": customer.pet_size,
           "diet_rule": customer.diet_rule, "pets": " ".join(customer.pets),
           # ADR 0039: the month the churn hazard ended the customer's history.
           "churn_month": customer.churn_month,
           # ADR 0044: whether the shop may record this customer's behaviour.
           "consent_behavioural": customer.consent_behavioural}
    row.update({trait: getattr(customer, trait) for trait in HIDDEN_TRAITS})
    row.update({f"{s}_sensitivity": customer.sensitivities[s] for s in SENSITIVITIES})
    # The personalised-search benchmark's ceiling re-scores products with the
    # generator's own weight, which reads the favourite brands (ADR 0037 §3).
    row["favorite_brands"] = list(customer.favorite_brands)
    return {k: v for k, v in row.items() if v is not None}


@dataclass
class Context:
    """One visit: a moment products were shown, or a landing that bounced.

    A visitor who hasn't bought yet has no `customer` (ADR 0040)."""
    context_id: str                 # "SESS-000001"
    customer: str | None            # link → customers.customer_id; None before a first order
    visitor: str                    # the device: "VIS-0012345"
    month: str
    weekday: str
    surface: str                    # search | for_you | category | bought_together | landing
    source: str                     # organic_search | paid_search | social | email | affiliate | direct
    landing: str                    # product | category | search | home | offer
    landing_category: str | None = None
    first_order: bool = False       # the visit ended in the visitor's first order
    # ADR 0038: derived visibly from the shopper's purchases in earlier months.
    offer_share: str = "none"       # none | low | high: bought on offer
    new_share: str = "none"         # … new products
    label_share: str = "none"       # … labelled products
    search_query: str | None = None
    basket: str | None = None              # this month's basket, SKUs
    basket_categories: str | None = None   # the same as words: "small_animal_cage dog_dryfood"
    prev_basket: str | None = None         # the last order before this month, SKUs
    owned: str | None = None               # kit items owned from earlier orders: "small_animal_cage"


def kit_sequence(pet: str) -> tuple[str, ...]:
    """The kit in the order a household completes it: starter kit, then add-ons."""
    return lifecycle.STARTER_KITS.get(pet, ()) + lifecycle.ADD_ONS.get(pet, ())


def kit_status(product: dict, basket: set[str], owned: set[str]) -> str | None:
    """Where a shown kit item stands in the household's kit: "owned", "next"
    (the kit's next missing item), "other" (another add-on not yet owned),
    or None (not a kit item, or the household has no kit for its pet).

    `product` is a products.json-style row; `basket` and `owned` are kit
    tokens ("small_animal_cage"). The kit counts as started when any of its
    items is in the basket or owned."""
    pet = product["pet_type"]
    kind = lifecycle.item_type(product["name"], product["brand"])
    sequence = kit_sequence(pet)
    if kind not in sequence:
        return None
    have = {k for k in sequence if shoppers.token(pet, k) in basket | owned}
    if not have:
        return None
    if kind in have:
        return "owned"
    if kind == next(k for k in sequence if k not in have):
        return "next"
    return "other" if kind in lifecycle.ADD_ONS.get(pet, ()) else None


def kit_odds(product: dict, basket: set[str], owned: set[str]) -> float:
    """K1: how much the household's place in its kit moves this shown product."""
    return {"owned": OWNED_KIT_ODDS, "next": NEXT_KIT_ODDS, "other": OTHER_ADD_ON_ODDS}.get(
        kit_status(product, basket, owned), 1.0)


# ADR 0038: what a shop can see of a sensitivity is what the shopper bought.
# A share at or above this is `high` (for new products, any purchase is).
SHARE_HIGH_AT = {"offer": 0.4, "label": 0.25}


def share_band(kind: str, matching: int, bought: int) -> str:
    """`offer_share`, `new_share`, `label_share`: of the shopper's purchases
    in earlier months, the share bought on offer, new, or labelled."""
    if bought == 0:
        return "none"
    if kind == "new":
        return "high" if matching > 0 else "low"
    return "high" if matching / bought >= SHARE_HIGH_AT[kind] else "low"
