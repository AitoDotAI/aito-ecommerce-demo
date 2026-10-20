"""Why this product, for this shopper: reasons read from `_recommend`'s `$why`.

A `_recommend` hit's `$why` (no `basedOn`) holds, among its factors, the
lift of the product itself:

    {"type": "hitPropositionLift",
     "proposition": {"product_sku": {"$has": "SKU-PT-0553"}},
     "value": 7.97,
     "factors": [{"type": "relatedPropositionLift",
                  "proposition": {"context.month": "2026-04"}, "value": 1.32},
                 {"type": "relatedPropositionLift",
                  "proposition": {"$group": [{"$and": [{"context.basket_categories": …}]}]},
                  "value": 2.38}, …]}

The nested factors are how much each part of the `where` lifts *this*
product: the reasons behind the probability the card shows. The `where`
holds only what a shop observes (ADR 0033): the customer, the month, the
cart and the kit the household owns. The cart can appear as several
factors (its SKUs, its categories); they multiply into one "your cart"
reason. (The nesting was probed 2026-10-17 on the shape before ADR 0033;
`tests/test_aito_check.py` checks the context form live.)

A product with too few impressions of its own has no such lift: its
`$why` holds only `hitLinkPropositionLift`, the prior from its features
(1 of the 60 top hits for a grain-free household, 2026-10-17). Aito has
nothing to break down, so the card shows no reasons.
"""

from __future__ import annotations

import calendar
import json
from dataclasses import dataclass

from src.aito_client import AitoError

# A reason smaller than this isn't worth a chip: ×1.1 is noise in a demo.
MIN_REASON_LIFT = 1.15
MAX_REASONS = 3

CART = "Goes with your cart"
KIT = "Fits the kit you have"
HISTORY = "Your own history"
# Declared fields, if Aito expands the customer link into them.
DECLARED_LABELS = {
    "context.customer.pets": "Your pets",
    "context.customer.dog_size": "Your dog's size",
    "context.customer.diet": "Your diet",
    "context.customer.region": "Region",
}


@dataclass(frozen=True)
class Reason:
    label: str    # "Goes with your cart", "Fits the kit you have", "Sells in April"
    lift: float   # how much it multiplies this product's odds of a purchase


def reasons_for(why: dict, sku: str) -> list[Reason]:
    """The largest lifts behind `sku`'s probability, each at least MIN_REASON_LIFT."""
    own = [f for f in why["factors"]
           if f["type"] == "hitPropositionLift" and f["proposition"] == {"product_sku": {"$has": sku}}]
    if not own:
        return []
    if len(own) > 1:
        raise AitoError(f"$why for {sku} has {len(own)} lifts of the product itself, expected one: "
                        f"{json.dumps(why)[:300]}")
    lifts: dict[str, float] = {}
    for factor in own[0].get("factors", []):
        label = _label(factor["proposition"])
        if label is not None:
            lifts[label] = lifts.get(label, 1.0) * float(factor["value"])
    reasons = [Reason(label, round(lift, 2)) for label, lift in lifts.items() if lift >= MIN_REASON_LIFT]
    return sorted(reasons, key=lambda r: -r.lift)[:MAX_REASONS]


def _label(proposition: dict) -> str | None:
    """A reason's label, or None for a part of the `where` that isn't a reason
    to show (`just_bought: false`: the grid asks every product that way), or
    for a `$group`: Aito's joint estimate of several conditions, which can rest
    on no rows at all; until `$why` reports support
    (td-20261020210945585150), a card shows only single-condition lifts."""
    if "$group" in proposition:
        return None
    text = json.dumps(proposition)
    if "context.basket" in text:
        return CART
    if "context.owned" in text:
        return KIT
    if len(proposition) != 1:
        raise AitoError(f"Unexpected $why proposition: {text[:200]}")
    [(field, value)] = proposition.items()
    if field == "just_bought":
        return None
    if field == "context.month":
        return f"Sells in {calendar.month_name[int(value[5:7])]}"
    if field == "context.customer":
        return HISTORY
    if field in DECLARED_LABELS and isinstance(value, str):
        return f"{DECLARED_LABELS[field]}: {value.replace('_', ' ')}"
    raise AitoError(f"Unexpected $why proposition: {text[:200]}")
