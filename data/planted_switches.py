"""One switch per planted effect of ADRs 0038–0040, and the seeded RNGs they draw from.

Every effect is judged against a null generation: the same seed with its
switch off (docs/verification/actionable-states-prereg.md). Every switch is
on in the committed fixtures; `scripts/planted_effects.py` turns one off at a
time.

Each effect draws from an RNG of its own, keyed by the seed and the unit it
acts on (a customer, a month, a product, an impression). Switching one effect
off then leaves every other draw where it was ("common random numbers"), so a
planted ÷ null ratio measures the effect, not the noise of re-drawing
everything after it.
"""

from __future__ import annotations

import math
import random

ON: dict[str, bool] = {
    # ADR 0038: what moves an impression, by the shopper's hidden sensitivity.
    "P6": True,        # an offer, by discount sensitivity
    "P7": True,        # stars, by stars sensitivity (ADR 0039's R1 and R2)
    "P8": True,        # a new product, by newness sensitivity
    "P9": True,        # a label, by label sensitivity
    "P10": True,       # low stock lifts the purchase ("only a few left")
    # ADR 0039: one hidden cause, quality, and what follows from it.
    "quality": True,   # R2: a poor product converts ×0.6 whatever its stars
    "R3": True,        # the experience moves NPS
    "R4": True,        # a bad experience raises the churn hazard
    "R4_reply": True,  # a reply to the negative review halves that rise
    "R5": True,        # stars move demand (order pick weights)
    "R6": True,        # stars move price sensitivity
    # ADR 0040: where customers come from.
    "F1": True,        # sources land on different pages
    "F2": True,        # sources convert differently
    "F3": True,        # sources bring different sensitivities
    "F4": True,        # sources stay differently
    "F5": True,        # a staple in the first basket doubles the chance to stay
    # ADR 0045: the shop's ranker places an offered product higher.
    "placement": True,
    # ADR 0049, 0050: the list price and the listing as state (data release 3a).
    "L1": True,        # list price moves; promote products run extra offers
    "L2": True,        # the list price acts on the click at ε/3, on cart and purchase at ε
    "L3": True,        # an offer lifts the click at 0.4 of its lift on the purchase
    "L4": True,        # pictures
    "L5": True,        # description
    "L6": True,        # advertising
    # ADR 0039 amendment (release 3b): the experience flags a shop reads as churn tells.
    "A6": True,        # a late or damaged delivery raises the churn hazard
    "A7": True,        # a bad line is also returned, and a returned line raises the churn hazard
    # ADR 0051: which action works on whom (data release 3b).
    "actions": True,   # an action moves the 30-day outcome at all
    "A1": True,        # an email works on those who answered one, not on those who ignored them
    "A2": True,        # a discount works on those who buy on offer
    "A3": True,        # a voucher brings back the lapsed
    "A4": True,        # an ad reaches those who consented to tracking
    "A5": True,        # an apology works on an open issue
    # ADR 0044: what a person declares.
    "C1": True,        # declared interests follow the hidden traits
}

# Reviews written at all. Off only in `tests/test_review_chain.py`, which
# checks that churn doesn't read reviews except through the planted paths.
REVIEWS_WRITTEN = True


def stream(seed: int, *key) -> random.Random:
    """The RNG of one effect for one unit: `stream(42, "churn", "CUST-00007")`."""
    return random.Random(":".join(str(part) for part in (seed, *key)))


def poisson(rng: random.Random, mean: float) -> int:
    """A Poisson draw (Knuth's method, in chunks so `exp(-mean)` never underflows)."""
    assert mean >= 0, f"negative Poisson mean {mean}"
    total = 0
    while mean > 0:
        chunk = min(mean, 30.0)
        mean -= chunk
        limit, k, p = math.exp(-chunk), 0, rng.random()
        while p > limit:
            k += 1
            p *= rng.random()
        total += k
    return total
