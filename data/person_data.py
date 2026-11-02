"""What a shop can know about a person (ADR 0044).

- **Purchase form:** postcode area (first 3 digits, within the region),
  delivery method, and sex if they filled it in (about 55 %). Sex moves
  nothing (C3).
- **Account:** a loyalty membership.
- **Declared interests:** topics from a fixed list, chosen by about 35 %.
  They are declared consistently with the hidden traits (C1): someone who
  says "natural food" is mostly a grain-free household or health-focused.
- **Behavioural consent** (about 60 %), independent of every hidden trait
  (C2). Without it, the shop records no visits or impressions; orders
  still exist.
- **A pet profile** (pets, a dog's size), filled by about 40 %.

Each draw has its own seeded RNG per customer (`data/planted_switches.py`).
Checks: docs/verification/actionable-states-prereg.md, ADR 0044 addendum.
"""

from __future__ import annotations

import random

from data.planted_switches import ON, stream

CONSENT_P = 0.6
SEX_FILLED_P = 0.55
SEXES = {"female": 0.50, "male": 0.47, "other": 0.03}
POSTCODE_AREAS = {"helsinki": range(1, 10), "espoo": range(20, 29), "turku": range(200, 210),
                  "tampere": range(330, 340), "jyvaskyla": range(400, 410), "oulu": range(900, 910)}
DELIVERY_METHODS = {"home_delivery": 0.45, "parcel_locker": 0.40, "store_pickup": 0.15}
LOYALTY_P = 0.4
PET_PROFILE_P = 0.4              # Antti, 2026-10-24: most people never fill a pet profile

INTEREST_DECLARED_P = 0.35
TOPICS = ("training", "grooming", "natural_food", "toys_and_play", "health_and_care", "budget_buys")
NULL_TOPIC_P = 0.3               # C1's null: every topic alike, whatever the traits


def _choose(rng: random.Random, weights: dict[str, float]) -> str:
    return rng.choices(list(weights), weights=list(weights.values()), k=1)[0]


def topic_probabilities(customer) -> dict[str, float]:
    """C1: how likely a declaring customer is to pick each topic, from their hidden traits."""
    if not ON["C1"]:
        return {topic: NULL_TOPIC_P for topic in TOPICS}
    if customer.diet_rule == "grain-free":
        natural = 0.95
    else:
        natural = 0.40 if customer.health_focus == "high" else 0.05
    return {
        "natural_food": natural,
        "budget_buys": 0.6 if customer.lifestyle == "budget" else 0.1,
        "toys_and_play": 0.6 if customer.treat_affinity == "high" else 0.15,
        "health_and_care": 0.5 if customer.health_focus == "high" else 0.15,
        "grooming": 0.25,
        "training": 0.25,
    }


def draw_interests(rng: random.Random, customer) -> str | None:
    """The topics a customer chose on their preferences page, or None. One
    uniform per topic, always drawn, so C1's null re-uses the same draws."""
    declares = rng.random() < INTEREST_DECLARED_P
    probabilities = topic_probabilities(customer)
    chosen = [t for t in TOPICS if rng.random() < probabilities[t]]
    fallback = rng.choice([t for t in TOPICS if t != "natural_food"])
    if not declares:
        return None
    return " ".join(chosen or [fallback])


def assign_consent(seed: int, customers: list, always_consenting: set[str]) -> None:
    """Behavioural consent, before any session: it decides what is recorded (ADR 0045)."""
    for c in customers:
        c.consent_behavioural = (c.customer_id in always_consenting
                                 or stream(seed, "consent", c.customer_id).random() < CONSENT_P)


def assign(seed: int, customers: list, always_with_profile: set[str]) -> None:
    """Fill each customer's declared fields. Runs after the orders, since the
    diet rule is drawn there."""
    for c in customers:
        cid = c.customer_id
        c.pet_profile = cid in always_with_profile or stream(seed, "pet-profile", cid).random() < PET_PROFILE_P
        form = stream(seed, "purchase-form", cid)
        filled, sex = form.random() < SEX_FILLED_P, _choose(form, SEXES)
        c.sex = sex if filled else None
        c.postcode_area = f"{form.choice(POSTCODE_AREAS[c.region]):03d}"
        c.delivery_method = _choose(form, DELIVERY_METHODS)
        c.loyalty_member = stream(seed, "loyalty", cid).random() < LOYALTY_P
        c.interests = draw_interests(stream(seed, "interests", cid), c)


def visitor_consents(seed: int, visitor: int) -> bool:
    """A never-buy visitor's cookie-banner answer: one per device."""
    return stream(seed, "consent", "visitor", visitor).random() < CONSENT_P
