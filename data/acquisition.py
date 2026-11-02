"""Where customers come from: sources, landing pages, first orders and who stays (ADR 0040).

A visitor is identified per device before they buy. Most visitors never buy:
their sessions are generated too, so conversion has a denominator. On a first
order the visitor becomes a customer, whose `first_source` is that session's.

The planted effects (docs/verification/actionable-states-prereg.md):

  F1  sources land differently (product pages, toys and treats, offers)
  F2  a new visitor's session converts at a rate set by its source
  F3  sources bring different sensitivities (`data/sensitivities.py`)
  F4  sources stay differently: the chance of 3+ orders in the first 6 months
  F5  a staple in the first basket doubles that chance, whatever the source
"""

from __future__ import annotations

import random

from data import lifecycle
from data.catalogue_events import add_months
from data.planted_switches import ON, poisson, stream

SOURCES = ("organic_search", "paid_search", "social", "email", "affiliate", "direct")
FIRST_SOURCE_SHARES = {"organic_search": 0.30, "paid_search": 0.20, "direct": 0.20,
                       "affiliate": 0.12, "email": 0.10, "social": 0.08}
RETURNING_SOURCE_SHARES = {"direct": 0.35, "email": 0.25, "organic_search": 0.20,
                           "paid_search": 0.10, "social": 0.05, "affiliate": 0.05}

CONVERSION = {"email": 0.06, "paid_search": 0.04, "organic_search": 0.03,       # F2
              "direct": 0.05, "affiliate": 0.035, "social": 0.012}

LANDINGS = ("product", "category", "search", "home", "offer")
LANDING_BY_SOURCE: dict[str, dict[str, float]] = {                                # F1
    "organic_search": {"product": 0.70, "search": 0.15, "category": 0.10, "home": 0.05},
    "paid_search":    {"product": 0.40, "search": 0.30, "category": 0.20, "home": 0.10},
    "social":         {"product": 0.40, "category": 0.30, "home": 0.20, "offer": 0.10},
    "email":          {"offer": 0.60, "home": 0.20, "product": 0.10, "category": 0.10},
    "affiliate":      {"offer": 0.60, "product": 0.30, "category": 0.10},
    "direct":         {"home": 0.60, "search": 0.20, "category": 0.10, "product": 0.10},
}
# F1's null: one landing mix for every source.
POOLED_LANDING = {"product": 0.35, "offer": 0.20, "home": 0.20, "category": 0.13, "search": 0.12}
SOCIAL_TOYS_AND_TREATS_P = 0.55
TOYS_AND_TREATS = ("toys", "treats")

STAY_FACTOR = {"organic_search": 1.4, "email": 1.2, "direct": 1.0,                 # F4
               "paid_search": 0.9, "social": 0.6, "affiliate": 0.5}
STAPLE_FIRST_BASKET_FACTOR = 2.0                                                   # F5
# Chosen so the share who become regular stays at today's 52 % (seed 42).
REGULAR_BASE_P = 0.315
REGULAR_WINDOW_MONTHS = 6
REGULAR_MIN_ORDERS = 3
FIRST_ORDER_STAPLE_P = 0.6       # else the household starts its staples with the 2nd order

BOUNCE_P = 0.8                   # a never-buy session that leaves without seeing products
LANDING_PAGE_PRODUCTS = (2, 4)   # how many products a landing page shows
EXTRA_SESSION_P = (0.30, 0.08)   # a never-buy visitor's 2nd and 3rd session


def _choose(rng: random.Random, weights: dict[str, float]) -> str:
    return _at(rng.random(), weights)


def _at(u: float, weights: dict[str, float]) -> str:
    """The key whose share of the cumulative weights holds `u` (in [0, 1))."""
    total, edge = sum(weights.values()), 0.0
    for key, weight in weights.items():
        edge += weight / total
        if u < edge:
            return key
    return key


def draw_first_source(rng: random.Random) -> str:
    return _choose(rng, FIRST_SOURCE_SHARES)


def draw_returning_source(rng: random.Random) -> str:
    return _choose(rng, RETURNING_SOURCE_SHARES)


def draw_landing(rng: random.Random, source: str, interest_category: str) -> tuple[str, str | None]:
    """(landing page, its category) for a session from `source`. `interest_category`
    is the category the visitor came for. A home page has no category."""
    u_page, u_social, u_pick = rng.random(), rng.random(), rng.random()
    mix = LANDING_BY_SOURCE[source] if ON["F1"] else POOLED_LANDING
    landing = _at(u_page, mix)
    if landing == "home":
        return landing, None
    if ON["F1"] and source == "social" and u_social < SOCIAL_TOYS_AND_TREATS_P:
        return landing, TOYS_AND_TREATS[int(u_pick * len(TOYS_AND_TREATS))]
    return landing, interest_category


def conversion(source: str) -> float:
    """F2: the share of a new visitor's sessions from `source` that end in a first order."""
    if ON["F2"]:
        return CONVERSION[source]
    # The pooled rate: the same sessions overall, one rate for every source.
    return 1.0 / sum(share / CONVERSION[s] for s, share in FIRST_SOURCE_SHARES.items())


STAPLE_LINE_CATEGORIES = frozenset({"dry-food", "wet-food", "litter", "aquarium"})


def is_staple_line(product) -> bool:
    """Food or litter the household restocks (fish food, not filters): F5's staple."""
    return product.category in STAPLE_LINE_CATEGORIES and lifecycle.is_staple(product, product.pet_type)


def regular_probability(first_source: str, staple_in_first_basket: bool) -> float:
    p = REGULAR_BASE_P
    if ON["F4"]:
        p *= STAY_FACTOR[first_source]
    if ON["F5"] and staple_in_first_basket:
        p *= STAPLE_FIRST_BASKET_FACTOR
    return min(p, 0.95)


def plan_first_months(rng: random.Random, plan: list[str], first_month: str, eligible: list[str],
                      regular: bool) -> list[str]:
    """The order months after the first, so that a regular customer has at least 3
    orders in their first 6 months and anyone else at most 2. Later months stay."""
    window = [m for m in eligible if first_month < m < add_months(first_month, REGULAR_WINDOW_MONTHS)]
    inside = [m for m in plan if m in window]
    outside = [m for m in plan if m not in window]
    wanted = REGULAR_MIN_ORDERS - 1
    if regular and len(inside) < wanted:
        free = [m for m in window if m not in inside]
        inside += rng.sample(free, min(len(free), wanted - len(inside)))
    elif not regular and len(inside) >= wanted:
        inside = rng.sample(inside, wanted - 1)
    return sorted(inside + outside)


def never_buy_sessions(seed: int, first_orders: dict[tuple[str, str], int]) -> list[tuple[str, str, int]]:
    """The sessions of visitors who never buy, as (source, month, visitor number).

    For each source and month, Poisson(n · (1/c − 1)) sessions, where n is that
    month's first orders from the source and c its conversion: then the first
    orders are a share c of all new-visitor sessions. A visitor has 1–3 sessions."""
    sessions: list[tuple[str, str, int]] = []
    visitor = 0
    for (source, month), n in sorted(first_orders.items()):
        rng = stream(seed, "never-buy", source, month)
        remaining = poisson(rng, n * (1.0 / conversion(source) - 1.0))
        while remaining > 0:
            u = rng.random()
            k = min(remaining, 1 + (u < EXTRA_SESSION_P[0]) + (u < EXTRA_SESSION_P[1]))
            sessions += [(source, month, visitor)] * k
            remaining -= k
            visitor += 1
    return sessions
