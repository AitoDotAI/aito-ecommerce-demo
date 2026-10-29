"""Reviews with consequences: one hidden cause, in one direction (ADR 0039).

    quality (hidden, per product)
       └─► the experience of each order line (bad / ok / good), and a delivery incident per order
              ├─► a review, sometimes; its stars become the product's band for later months
              │      ├─► clicks and purchases (P7, `data/sensitivities.py`)
              │      ├─► demand: an order's pick weight (R5)
              │      └─► price sensitivity (R6)
              ├─► NPS, when the order is surveyed (R3)
              └─► churn: a monthly hazard, raised after a bad experience (R4)

Nothing here reads whether a customer churns: churn follows from the
experiences, never the other way round. The generator runs month by month, so
an order sees the stars of the reviews written before its month
(`StarsSoFar`). Thresholds: docs/verification/actionable-states-prereg.md.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass, field

from data import shoppers
from data.planted_switches import ON

# Cumulative hash cut-offs: poor 8 %, ok 42 %, good 40 %, excellent 10 %.
QUALITY_CUTOFFS = ((8, "poor"), (50, "ok"), (90, "good"), (100, "excellent"))
POOR_QUALITY_ODDS = 0.6          # R2: on the cart and purchase steps, whatever the stars

EXPERIENCE_BY_QUALITY: dict[str, dict[str, float]] = {
    "poor":      {"bad": 0.45, "ok": 0.40, "good": 0.15},
    "ok":        {"bad": 0.06, "ok": 0.54, "good": 0.40},
    "good":      {"bad": 0.02, "ok": 0.33, "good": 0.65},
    "excellent": {"bad": 0.01, "ok": 0.14, "good": 0.85},
}
INCIDENT_P = 0.06                # a late or damaged delivery, per order

REVIEW_P = {"bad": 0.25, "ok": 0.08, "good": 0.15}
RATING_BY_EXPERIENCE: dict[str, dict[int, float]] = {
    "bad":  {1: 0.50, 2: 0.35, 3: 0.15},
    "ok":   {2: 0.10, 3: 0.50, 4: 0.40},
    "good": {4: 0.30, 5: 0.70},
}
# The category follows the stars, so a review's text reads like its rating.
CATEGORY_BY_RATING: dict[int, dict[str, float]] = {
    1: {"quality": 0.40, "shipping": 0.32, "fit": 0.20, "question": 0.08},
    2: {"quality": 0.40, "shipping": 0.32, "fit": 0.20, "question": 0.08},
    3: {"question": 0.35, "quality": 0.25, "shipping": 0.20, "fit": 0.20},
    4: {"praise": 0.70, "question": 0.20, "quality": 0.05, "fit": 0.05},
    5: {"praise": 0.90, "question": 0.10},
}
REPLY_P = 0.40                   # of negative reviews, chosen at random

NPS_SURVEY_P = 0.30
NPS_BASE, NPS_SD = 8.0, 1.5
NPS_BAD_EXPERIENCE = -3.5
NPS_INCIDENT = -2.0
NPS_ALL_GOOD = 0.7
NPS_REPLY = 2.0                  # a reply to the respondent's negative review of the order

CHURN_RISE = 3.0                 # R4: the hazard after a bad experience (1.8 before release 3b) …
CHURN_RISE_REPLIED = 2.0         # … lower when the negative review was replied to
CHURN_RISE_MONTHS = 3
INCIDENT_CHURN_RISE = 3.0        # A6: a late or damaged delivery raises the hazard too, for the same 3 months
RETURN_CHURN_RISE = 2.5          # A7: so does each returned line of the order
BAD_EXPERIENCE_RETURN_P = 0.12   # A7: a line that went badly is also returned (on top of the base rate) …
RETURN_THIN_P = 0.25            # … and a share of the other returns is dropped, to keep the share near 2.75 %

# A9: one hidden trait per customer, how satisfied they tend to be (z, standard normal). It is a shared
# cause: it moves their NPS answers and review ratings and, in the other direction, their churn hazard,
# so an unhappy answer predicts leaving the way it does in a shop. Churn still reads no observable.
SATISFACTION_NPS_SD = 1.1        # the trait's part of an answer; with NPS_NOISE_SD about the old NPS_SD in all
NPS_NOISE_SD = 1.0
SATISFACTION_CHURN_K = 0.9       # hazard × exp(−K·z), divided by its mean exp(K²/2)
RATING_SHIFT_Z = 0.8             # beyond ±0.8 a writer rates one star lower or higher than the experience gives
UNHAPPY_REVIEW_FACTOR = 1.5      # and an unhappy customer writes more of them

RATING_PICK_FACTOR = {"5": 1.3, "1-2": 0.6}       # R5
RATING_ELASTICITY = {"5": -1.0, "1-2": -2.4}      # R6


def quality(sku: str) -> str:
    """Fixed per SKU from a hash, not an RNG, so tests can name the same products."""
    bucket = int(hashlib.md5(sku.encode()).hexdigest(), 16) % 100
    return next(level for cutoff, level in QUALITY_CUTOFFS if bucket < cutoff)


def _choose(rng: random.Random, weights: dict):
    return rng.choices(list(weights), weights=list(weights.values()), k=1)[0]


def draw_experience(rng: random.Random, sku: str) -> str:
    return _choose(rng, EXPERIENCE_BY_QUALITY[quality(sku)])


def order_experience(line_experiences: list[str]) -> str:
    """An order is as good as its worst line."""
    for level in ("bad", "ok"):
        if level in line_experiences:
            return level
    return "good"


@dataclass
class DrawnReview:
    rating: int
    category: str
    replied: bool


def satisfaction(seed: int, customer_id: str) -> float:
    """The customer's hidden satisfaction trait (A9); 0 when the effect is off."""
    return random.Random(f"{seed}:satisfaction:{customer_id}").gauss(0.0, 1.0) if ON["A9"] else 0.0


def churn_factor(z: float) -> float:
    """What the trait does to the monthly churn hazard: below 1 for the satisfied, above for the unhappy."""
    return math.exp(-SATISFACTION_CHURN_K * z) / math.exp(SATISFACTION_CHURN_K ** 2 / 2) if ON["A9"] else 1.0


def draw_review(review_rng: random.Random, reply_rng: random.Random, experience: str,
                z: float = 0.0) -> DrawnReview | None:
    """Whether this line's buyer reviews it, and how. Reads the experience and the writer's trait."""
    chance = REVIEW_P[experience] * (UNHAPPY_REVIEW_FACTOR if ON["A9"] and z <= -RATING_SHIFT_Z else 1.0)
    if review_rng.random() >= chance:
        return None
    rating = _choose(review_rng, RATING_BY_EXPERIENCE[experience])
    if ON["A9"]:
        rating = max(1, rating - 1) if z <= -RATING_SHIFT_Z else min(5, rating + 1) if z >= RATING_SHIFT_Z else rating
    category = _choose(review_rng, CATEGORY_BY_RATING[rating])
    replied = rating <= 2 and reply_rng.random() < REPLY_P
    return DrawnReview(rating, category, replied)


def nps_score(rng: random.Random, experience: str, incident: bool, replied_negative: bool,
              z: float = 0.0) -> int | None:
    """The order's NPS score, or None if it wasn't surveyed. Both draws are
    always made, so a null changes the score, never who was surveyed."""
    surveyed = rng.random() < NPS_SURVEY_P
    score = rng.gauss(NPS_BASE + SATISFACTION_NPS_SD * z, NPS_NOISE_SD) if ON["A9"] else rng.gauss(NPS_BASE, NPS_SD)
    if ON["R3"]:
        score += NPS_BAD_EXPERIENCE if experience == "bad" else 0.0
        score += NPS_INCIDENT if incident else 0.0
        score += NPS_ALL_GOOD if experience == "good" else 0.0
        score += NPS_REPLY if replied_negative else 0.0
    return round(min(10.0, max(0.0, score))) if surveyed else None


def nps_group(score: int) -> str:
    return "promoter" if score >= 9 else "passive" if score >= 7 else "detractor"


def churn_rise(replied: bool) -> float:
    """How much one bad experience multiplies the monthly churn hazard, for 3 months."""
    if not ON["R4"]:
        return 1.0
    return CHURN_RISE_REPLIED if replied and ON["R4_reply"] else CHURN_RISE


@dataclass
class StarsSoFar:
    """The stars each product's reviews gave, through the last closed month.

    The order loop closes a month once every order in it is drawn, so an
    order sees only reviews written before its own month."""
    ratings: dict[str, list[int]] = field(default_factory=dict)
    pending: list[tuple[str, int]] = field(default_factory=list)

    def add(self, sku: str, rating: int) -> None:
        self.pending.append((sku, rating))

    def close_month(self) -> None:
        for sku, rating in self.pending:
            self.ratings.setdefault(sku, []).append(rating)
        self.pending.clear()

    def band(self, sku: str) -> str:
        ratings = self.ratings.get(sku)
        return shoppers.rating_band(sum(ratings) / len(ratings) if ratings else None)

    def count(self, sku: str) -> int:
        return len(self.ratings.get(sku, []))

    def pick_factor(self, sku: str) -> float:
        return rating_pick_factor(self.band(sku))

    def elasticity(self, sku: str, own: float) -> float:
        return rating_elasticity(self.band(sku), own)


def rating_pick_factor(band: str) -> float:
    """R5: the shop's ranker shows a well-rated product more, a badly rated one less."""
    return RATING_PICK_FACTOR.get(band, 1.0) if ON["R5"] else 1.0


def rating_elasticity(band: str, own: float) -> float:
    """R6: a well-rated product holds its units through a list-price change."""
    return RATING_ELASTICITY.get(band, own) if ON["R6"] else own
