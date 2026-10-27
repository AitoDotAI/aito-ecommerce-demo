"""Shoppers who react differently, and how a product's state moves each (ADR 0038).

Each shopper draws four hidden sensitivities, `high`, `mid` or `low`: to a
discount, to stars, to newness and to labels. No table Aito reads holds them
(ADR 0033); they are in the answer key, and the shop sees only what they
cause. The planted effects (docs/verification/actionable-states-prereg.md):

  P6   an offer lifts cart and purchase ×(1 + k · discount_pct / 10), the click by 0.4 of that (ADR 0049's L3)
  P7   stars, 5 against 1–2 (ADR 0039's R1 and R2)
  P8   a product in its first months on sale
  P9   a label: recommended, staff pick or popular
  P10  low stock lifts the purchase step only, for every shopper
"""

from __future__ import annotations

import math
import random

from data.planted_switches import ON

LEVELS = ("high", "mid", "low")

# P(high, mid, low) before the correlations below.
BASE_RATES: dict[str, tuple[float, float, float]] = {
    "discount": (0.30, 0.45, 0.25),
    "stars":    (0.30, 0.50, 0.20),
    "newness":  (0.20, 0.50, 0.30),
    "labels":   (0.25, 0.50, 0.25),
}
HIGH_RATE_CAP = 0.9
BUDGET_DISCOUNT_HIGH = 2.0       # a budget shopper is discount-high at 2× the rate
HEALTH_STARS_HIGH = 1.5          # a health-focused one stars-high at 1.5×
FLEXIBLE_NEWNESS_HIGH = 2.0      # a brand-flexible one newness-high at 2×
AFFILIATE_DISCOUNT_HIGH = 2.5    # F3 (ADR 0040): coupon sites bring discount hunters
SOCIAL_NEWNESS_HIGH = 2.0        # F3: social brings shoppers who chase what's new

OFFER_K = {"high": 1.0, "mid": 0.4, "low": 0.1}                                  # P6
STARS_ODDS = {"high": {"5": 1.7, "1-2": 0.45},                                   # P7
              "mid":  {"5": 1.25, "1-2": 0.8},
              "low":  {"5": 1.05, "1-2": 0.95}}
UNRATED_ODDS = 0.9               # as ADR 0032's P4, for everyone
NEW_ODDS = {"high": 2.2, "mid": 1.3, "low": 0.9}                                 # P8
LABEL_ODDS = {"high": {"recommended": 1.8, "staff_pick": 1.6, "popular": 1.7},   # P9
              "mid":  {"recommended": 1.25, "staff_pick": 1.25, "popular": 1.25},
              "low":  {"recommended": 1.0, "staff_pick": 1.0, "popular": 1.0}}
CLICK_SHARE_OF_OFFER = 0.4       # L3 (ADR 0049): an offer's lift on the click, against its lift on the purchase
LOW_STOCK_PURCHASE_ODDS = 1.25                                                   # P10


def high_rate_factors(lifestyle: str, health_focus: str, brand_loyalty: str,
                      first_source: str | None) -> dict[str, float]:
    """How much likelier than the base rate this shopper is `high` on each sensitivity."""
    factors = {
        "discount": BUDGET_DISCOUNT_HIGH if lifestyle == "budget" else 1.0,
        "stars": HEALTH_STARS_HIGH if health_focus == "high" else 1.0,
        "newness": FLEXIBLE_NEWNESS_HIGH if brand_loyalty == "flexible" else 1.0,
        "labels": 1.0,
    }
    if ON["F3"] and first_source == "affiliate":
        factors["discount"] *= AFFILIATE_DISCOUNT_HIGH
    if ON["F3"] and first_source == "social":
        factors["newness"] *= SOCIAL_NEWNESS_HIGH
    return factors


def level_rates(sensitivity: str, high_factor: float) -> tuple[float, float, float]:
    """P(high, mid, low): `high` scaled (and capped), the rest split as in the base rates."""
    high, mid, low = BASE_RATES[sensitivity]
    scaled = min(HIGH_RATE_CAP, high * high_factor)
    rest = 1.0 - scaled
    return scaled, rest * mid / (mid + low), rest * low / (mid + low)


def draw_sensitivities(rng: random.Random, lifestyle: str, health_focus: str, brand_loyalty: str,
                       first_source: str | None) -> dict[str, str]:
    """One uniform per sensitivity, so a null that changes a rate flips only the
    shoppers near its edge."""
    factors = high_rate_factors(lifestyle, health_focus, brand_loyalty, first_source)
    drawn = {}
    for sensitivity in BASE_RATES:
        high, mid, _ = level_rates(sensitivity, factors[sensitivity])
        u = rng.random()
        drawn[sensitivity] = "high" if u < high else "mid" if u < high + mid else "low"
    return drawn


def stars_odds(rating_band: str, level: str) -> float:
    """P7: 4 stars sits halfway (geometrically) between 3 and 5."""
    if not ON["P7"]:
        return 1.0
    if rating_band == "5":
        return STARS_ODDS[level]["5"]
    if rating_band == "4":
        return math.sqrt(STARS_ODDS[level]["5"])
    if rating_band == "1-2":
        return STARS_ODDS[level]["1-2"]
    return UNRATED_ODDS if rating_band == "unrated" else 1.0


def state_odds(state, sensitivities: dict[str, str]) -> tuple[float, float, float]:
    """(click odds, cart-and-purchase odds, purchase-only odds) that this month's
    state of a product gives one shopper. `state` is a `ProductState`."""
    offer = 0.0
    if ON["P6"] and state.on_offer:
        offer = OFFER_K[sensitivities["discount"]] * state.discount_pct / 10.0
    # Every other lever is seen before the click, so it scales all three steps.
    others = stars_odds(state.rating_band, sensitivities["stars"])
    if ON["P8"] and state.age == "new":
        others *= NEW_ODDS[sensitivities["newness"]]
    if ON["P9"] and state.label != "none":
        others *= LABEL_ODDS[sensitivities["labels"]][state.label]
    purchase_only = LOW_STOCK_PURCHASE_ODDS if ON["P10"] and state.stock == "low" else 1.0
    # ADR 0049 (L3): a click is cheap, so an offer lifts it less than the purchase.
    click_offer = CLICK_SHARE_OF_OFFER * offer if ON["L3"] else offer
    return others * (1.0 + click_offer), others * (1.0 + offer), purchase_only
