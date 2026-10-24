"""How much a product's state lifts a purchase, shop-wide (ADR 0043).

One `_predict purchased` on `impressions` per band, with only the band in
the `where`, through the impression's `product_state` link:

    {"from": "impressions", "where": {"product_state.rating_band": "4"},
     "predict": "purchased", "select": ["$p", "feature", "$why"]}

The `true` hit's `$why` is the base rate, Aito's normalisers, and one
`relatedPropositionLift` for the band (v2 returns the String value bare):

    {"type": "relatedPropositionLift",
     "proposition": {"product_state.rating_band": "4"}, "value": 1.198}

Probed 2026-10-24 on env `observable` (Aito 2.11.8): each band's lift is
its observed purchase rate over the base rate (4 stars: 14.87 % of 31,368
showings against 12.41 % overall). The lifts are the same for every
product, so the Shop reads them once, in one `_batch` of nine.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.aito_client import AitoClient, AitoError
from src.discount_what_if import BANDS

DISCOUNT_FIELD = "product_state.discount_band"
RATING_FIELD = "product_state.rating_band"
RATING_BANDS = ("unrated", "1-2", "3", "4", "5")


@dataclass(frozen=True)
class StateLifts:
    discount: dict[str, float]      # {"none": 0.875, "20+": 1.588, ...}
    rating: dict[str, float]        # {"1-2": 0.699, "4": 1.198, ...}

    def offer_factor(self, band: str) -> float:
        """An offer band against no offer: the Shop's `$p` is learned mostly
        from showings at list price (83 % of them)."""
        return self.discount[band] / self.discount["none"]

    def rating_factor(self, band: str, before: str) -> float:
        """A star band against the one the product had before."""
        return self.rating[band] / self.rating[before]


def lift_body(field: str, band: str) -> dict:
    return {"from": "impressions", "where": {field: band}, "predict": "purchased",
            "select": ["$p", "feature", "$why"]}


def read_state_lifts(client: AitoClient) -> StateLifts:
    queries = [(DISCOUNT_FIELD, b) for b in BANDS] + [(RATING_FIELD, b) for b in RATING_BANDS]
    answers = client.batch([lift_body(field, band) for field, band in queries])
    lifts = {(field, band): band_lift(field, band, answer) for (field, band), answer in zip(queries, answers)}
    return StateLifts(discount={b: lifts[(DISCOUNT_FIELD, b)] for b in BANDS},
                      rating={b: lifts[(RATING_FIELD, b)] for b in RATING_BANDS})


def band_lift(field: str, band: str, answer: dict) -> float:
    """The band's own lift in the `true` hit's `$why`; raises if it isn't there."""
    hit = next((h for h in answer.get("hits", []) if h.get("feature") is True), None)
    if hit is None:
        raise AitoError(f"_predict purchased where {field}={band} had no `true` hit: {str(answer)[:300]}")
    factors = [f for f in hit["$why"].get("factors", [])
               if f["type"] == "relatedPropositionLift" and f["proposition"] == {field: band}]
    if len(factors) != 1:
        raise AitoError(f"$why for {field}={band} has {len(factors)} lifts of the band, expected one: "
                        f"{str(hit['$why'])[:300]}")
    return float(factors[0]["value"])
