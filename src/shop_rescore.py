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

from src import cache
from src.aito_client import AitoClient, AitoError
from src.demand_forecast import LATEST_MONTH
from src.shop_history import NEXT_MONTH
from src.shop_state_lifts import StateLifts, read_state_lifts

RESCORED = 40
STATE_MODES = ("offer", "change")


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


def state_rescore(client: AitoClient, items: list, month: str, mode: str) -> list:
    """`items` re-ranked by the state of their product in `month`, for the Shop's "state in the ranking" option.

    `offer`: score = $p × lift(this month's offer band) / lift(no offer), stars ignored.
    `change`: score = $p × what changed since last month: the offer band and the star band each against
    last month's. $p already carries the product's usual state, so only a change should move it.
    """
    if mode not in STATE_MODES:
        raise ValueError(f"state mode must be one of {STATE_MODES}, not {mode!r}")
    measured = [replace(item, measured_rank=rank) for rank, item in enumerate(items, start=1)]
    now = _states(client, [i.sku for i in items], month)
    before = _states(client, list(now), previous_month(month)) if mode == "change" else {}
    lifts = _month_lifts(client)
    adjusted = []
    for item in measured:
        if item.sku not in now:
            adjusted.append(item)
            continue
        last = before.get(item.sku, now[item.sku])      # a product with no row last month has no change
        adjusted.append(replace(item, adjustment=adjustment(
            item.p, now[item.sku], last if mode == "change" else {"rating_band": now[item.sku]["rating_band"]},
            lifts, offer_against=last["discount_band"] if mode == "change" else "none")))
    return sorted(adjusted, key=lambda i: -(i.adjustment.score if i.adjustment else i.p))


def _month_lifts(client: AitoClient) -> StateLifts:
    """The shop-wide lifts, read once per half hour and database: they are the same for every product and
    shopper, and nine `_predict`s are most of what the option adds to a request."""
    cached = cache.get(f"state-lifts:{client.env}")
    if cached:
        return StateLifts(**cached)
    lifts = read_state_lifts(client)
    cache.set(f"state-lifts:{client.env}", {"discount": lifts.discount, "rating": lifts.rating}, ttl=1800)
    return lifts


def previous_month(month: str) -> str:
    year, number = int(month[:4]), int(month[5:])
    return f"{year - 1}-12" if number == 1 else f"{year}-{number - 1:02d}"


def adjustment(p: float, state: dict, before: dict, lifts: StateLifts, offer_against: str = "none") -> ScoreAdjustment:
    """The offer band against `offer_against` (no offer in the sandbox), the star band against `before`'s."""
    offer = lifts.offer_factor(state["discount_band"]) / lifts.offer_factor(offer_against)
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
