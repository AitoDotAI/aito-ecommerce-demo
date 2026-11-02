"""How a shopping session shows products, and what makes one sell (ADR 0045).

Every sale is a purchase in a session. A session's page has up to three parts
(`impressions.placement`):

- **`buy_again`**: what the household came for (staples, the kit, the next
  add-on, a seasonal line), each bought with its intent probability;
- **`list`**: 6–14 products the shop's own ranker picked and ordered, on
  sessions that browse (the rest are `direct` reorders);
- **`checkout`**: a dental chew suggested after dog dry food (Signal #2).

Price acts in one place: each showing's odds (the offer by the shopper's
discount sensitivity, P6; the list price through ε, P3). The ranker adds a
second effect of an offer: an offered product is shown more and placed higher
(`placement`), and clicks fall with the slot (position bias).
Checks: docs/verification/actionable-states-prereg.md, ADR 0045 addendum.
"""

from __future__ import annotations

import math
import random

from data.planted_switches import ON

DIRECT_P = 0.3                    # a session that only reorders: no list
LIST_SIZE = (6, 14)
OFFER_PLACEMENT = {"none": 1.0, "10-15": 1.3, "15-20": 1.5, "20+": 1.8}
NEW_PLACEMENT = 2.0               # the shop features new arrivals (ADR 0032, P2's pull)
ORDER_NOISE_SIGMA = 0.5           # the ranker's order: its score × lognormal noise
POSITION_CLICK_DECAY = 0.9        # each slot down the list: × 0.9 on the click odds
SHOPPING_CLICK_ODDS = 2.0         # a session in a month the household shops
OWNED_DURABLE_ODDS = 0.02         # nobody needs a second cage (D3)
OUT_OF_ORDER_ADD_ON_ODDS = 0.2    # the kit's add-ons come in order (S2)
# D1 (ADR 0027): a household that settled on a food buys that one; another food
# of the same pet and category sells at the odds of the old re-pick's escape.
OTHER_FOOD_ODDS = 0.15            # 1 − lifecycle.STAPLE_LOYALTY

# The chance a buy-again item is bought, before its state's and price's odds.
INTENT_P = {"restock": 0.6, "first": 0.95, "kit": 0.95, "add_on": 0.9, "seasonal": 0.9, "checkout": 0.9}


def placement_factor(state) -> float:
    """How much more often the ranker shows a product this month for its offer."""
    return OFFER_PLACEMENT[state.discount_band] if ON["placement"] else 1.0


def list_order(rng: random.Random, shown: list, score) -> list:
    """The ranker's order: by its score, with noise so the order isn't the score."""
    keyed = [(score(p) * math.exp(rng.gauss(0.0, ORDER_NOISE_SIGMA)), i, p) for i, p in enumerate(shown)]
    return [p for _, _, p in sorted(keyed, key=lambda t: (-t[0], t[1]))]


def position_click_odds(position: int) -> float:
    return POSITION_CLICK_DECAY ** position


def list_price_odds(raised_since: float, elasticity: float) -> float:
    """P3: a list price above the original sells less, by the product's ε (R6)."""
    return raised_since ** elasticity if raised_since != 1.0 else 1.0
