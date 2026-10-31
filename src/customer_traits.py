"""What a customer's purchase history says about how they shop (ADR 0053).

Every trait is observed, never inferred about the person: a share of the lines they bought, counted
the same way for everyone. Three are about how they choose (on offer, the cheaper half, well-rated),
two about the pets they buy for (which pets, which diets the food is made for). Nothing here reads
or guesses anything about the person themselves: no health, religion, ethnicity or the like, so the diet
traits are the pet's, taken from the product's `dietary` tag.

A customer is profiled only if they gave `consent_behavioural`; the others are counted, not profiled.
A trait needs `MIN_LINES` purchased lines, or it is "too few purchases" and not a guess.
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass

MIN_LINES = 3
# Same cut points as `offer_buyer` in the action table (data/customer_actions.py), so the two agree.
OFFER_EDGES = (0.20, 0.40)
VALUE_FROM = 0.65            # at least this share of the lines in the cheaper half of their category (about the top fifth)
PREMIUM_UP_TO = 0.35         # at most this share (about the bottom quarter)
RATING_LED_FROM = 0.25       # buys products this many stars above their category's average
LOW_RATED_BELOW = 0.0
DIET_MIN_LINES = 2           # a diet tag counts after this many lines of it
TOO_FEW = "too few purchases"
NOT_PROFILED = "not profiled"


@dataclass(frozen=True)
class Reference:
    """What a line is compared with: its category's median LIST price and average rating.

    The list price, not the price paid: the price trait asks what a customer chose, and a discount must not make a
    line look like a cheaper choice (that would build "buys on offer" into "buys the cheaper half")."""
    median_price: dict[tuple[str, str], float]
    mean_rating: dict[tuple[str, str], float]


def reference_for(products: list[dict], states: list[dict]) -> Reference:
    """`states` are the product states (one per product and month); their list prices set each category's median."""
    prices, ratings = defaultdict(list), defaultdict(list)
    by_sku = {p["sku"]: p for p in products}
    for state in states:
        product = by_sku[state["product_sku"]]
        prices[(product["category"], product["pet_type"])].append(state["list_price_eur"])
    for p in products:
        key = (p["category"], p["pet_type"])
        if p.get("avg_rating"):
            ratings[key].append(p["avg_rating"])
    return Reference({k: statistics.median(v) for k, v in prices.items()},
                     {k: statistics.mean(v) for k, v in ratings.items()})


def offer_band(share: float) -> str:
    return "rarely" if share < OFFER_EDGES[0] else "sometimes" if share < OFFER_EDGES[1] else "mostly"


def price_band(cheaper_share: float) -> str:
    return "value-leaning" if cheaper_share >= VALUE_FROM else "premium-leaning" if cheaper_share <= PREMIUM_UP_TO else "mixed"


def rating_band(gap: float) -> str:
    return "above-average ratings" if gap >= RATING_LED_FROM else "below-average ratings" if gap < LOW_RATED_BELOW else "average ratings"


def traits_for(customer: dict, lines: list[dict], products: dict[str, dict], states: dict[str, dict], ref: Reference) -> dict:
    """One customer's traits from the lines they bought. `lines` are order_lines already joined to this customer."""
    base = {"customer_id": customer["customer_id"], "name": customer["name"], "lines": len(lines),
            "pets_declared": customer.get("pets")}
    if not customer["consent_behavioural"]:
        return {**base, "profiled": False, "offer": NOT_PROFILED, "price": NOT_PROFILED, "rating": NOT_PROFILED,
                "pets": [], "diets": []}
    pets = sorted({products[ln["product_sku"]]["pet_type"] for ln in lines})
    diets = sorted(tag for tag, n in Counter(products[ln["product_sku"]].get("dietary") for ln in lines).items()
                   if tag and n >= DIET_MIN_LINES)
    if len(lines) < MIN_LINES:
        return {**base, "profiled": True, "offer": TOO_FEW, "price": TOO_FEW, "rating": TOO_FEW,
                "pets": pets, "diets": diets}
    on_offer = sum(states[ln["product_state"]]["on_offer"] for ln in lines) / len(lines)
    cheaper = sum(states[ln["product_state"]]["list_price_eur"] < ref.median_price[_key(products[ln["product_sku"]])] for ln in lines) / len(lines)
    gaps = [products[ln["product_sku"]]["avg_rating"] - ref.mean_rating[_key(products[ln["product_sku"]])]
            for ln in lines if products[ln["product_sku"]].get("avg_rating") and _key(products[ln["product_sku"]]) in ref.mean_rating]
    return {**base, "profiled": True,
            "offer": offer_band(on_offer), "offer_share": round(on_offer, 3),
            "price": price_band(cheaper), "cheaper_share": round(cheaper, 3),
            "rating": rating_band(statistics.mean(gaps)) if gaps else TOO_FEW,
            "rating_gap": round(statistics.mean(gaps), 2) if gaps else None,
            "pets": pets, "diets": diets}


def _key(product: dict) -> tuple[str, str]:
    return (product["category"], product["pet_type"])
