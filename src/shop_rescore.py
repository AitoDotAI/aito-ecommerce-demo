"""The Shop in the sandbox's next month: re-scored by the owner's levers (ADR 0043).

The Shop's ranking (`src/shop_ranking.py`) recommends products, and a
product's monthly state enters it only as history: a product the owner
has just put on offer would not move. So in sandbox mode, for 2026-05,
the Shop takes its top RESCORED candidates and re-scores the ones that
have a 2026-05 state (a lever was pulled on them):

    score = $p (the Shop's _recommend) × offer factor × star factor

- offer factor = lift(the state's discount band) / lift(no offer)
- star factor  = lift(the state's star band) / lift(its April star band)

The lifts are Aito's, read shop-wide from `$why` (`src/shop_state_lifts.py`).
The multiplication is this app's modelling choice, not one Aito query,
and the page says so. A re-scored card never shows Aito's `$why` beside
the new number: its explanation is Aito's probability, then the two
factors, multiplying out to the score shown. A product without a 2026-05
state keeps its `$p` as its score.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from src.aito_client import AitoClient, AitoError
from src.demand_forecast import LATEST_MONTH
from src.shop_history import NEXT_MONTH
from src.shop_state_lifts import StateLifts, read_state_lifts

RESCORED = 40


@dataclass(frozen=True)
class ScoreAdjustment:
    """Why a card's score differs from Aito's `$p`: two shop-wide factors."""
    aito_p: float               # the Shop's `_recommend` $p
    offer_band: str             # the 2026-05 state's discount band
    offer_factor: float         # lift(offer_band) / lift("none")
    rating_band: str            # the 2026-05 state's stars
    rating_band_before: str     # the April state's stars
    rating_factor: float        # lift(rating_band) / lift(rating_band_before)
    score: float                # aito_p × offer_factor × rating_factor


def rescore(client: AitoClient, items: list, month: str) -> list:
    """`items` (ShopItems ranked by $p) re-ranked by their 2026-05 state,
    each with its measured rank and, when re-scored, its adjustment."""
    if month != NEXT_MONTH:
        raise ValueError(f"The Shop is re-scored only for the sandbox's month {NEXT_MONTH}, not {month}")
    measured = [replace(item, measured_rank=rank) for rank, item in enumerate(items, start=1)]
    states = _states(client, [i.sku for i in items], NEXT_MONTH)
    if not states:
        return measured
    before = _states(client, list(states), LATEST_MONTH)
    lifts = read_state_lifts(client)
    adjusted = [replace(item, adjustment=adjustment(item.p, states[item.sku], before[item.sku], lifts))
                if item.sku in states else item
                for item in measured]
    return sorted(adjusted, key=lambda i: -(i.adjustment.score if i.adjustment else i.p))


def adjustment(p: float, state: dict, before: dict, lifts: StateLifts) -> ScoreAdjustment:
    offer = lifts.offer_factor(state["discount_band"])
    stars = lifts.rating_factor(state["rating_band"], before["rating_band"])
    return ScoreAdjustment(
        aito_p=p, offer_band=state["discount_band"], offer_factor=offer,
        rating_band=state["rating_band"], rating_band_before=before["rating_band"], rating_factor=stars,
        score=p * offer * stars,
    )


def _states(client: AitoClient, skus: list[str], month: str) -> dict[str, dict]:
    if not skus:
        return {}
    res = client.search("product_states", where={"month": month, "product_sku": {"$or": skus}}, limit=len(skus))
    if res["total"] > len(res["hits"]):
        raise AitoError(f"product_states has {res['total']} rows for {len(skus)} products in {month}: "
                        "more than one per product and month")
    return {row["product_sku"]: row for row in res["hits"]}
