"""Discount what-if on the Price view (ADR 0032): how likely a shopper is
to buy a product when it is shown, at each discount band.

One `_predict purchased` per band on `impressions`, with the product and
the band in the `where`:

    {"product_sku": "SKU-PT-0143", "product_state.discount_band": "20+"}

`product_state` links each impression to the product's state that month,
so the band is evidence like any other field, and works for a band the
product never had. That is the what-if.

Aito's `$why` for the `true` answer is a product: the base rate, its
normalisers, and one lift per fact (the band, the product). The rows
here multiply out to `$p`; `band_estimate` raises if they don't.

Beside each estimate, the product's own impressions at that band: how
often it was shown and bought, so a reader can see what the estimate
stands on. All of it is one `_batch`.

`$p` is shown as a rate because it matched the data: per band, within
10 % of the observed purchase rate in-sample and within 6 % on held-out
months (`docs/aito-cheatsheet.md`, "A discount band as a what-if").
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from src.aito_client import AitoClient, AitoError
from src.demand_forecast import LATEST_MONTH
from src.lookup_errors import UnknownProductError

BANDS = ("none", "10-15", "15-20", "20+")
BAND_FIELD = "product_state.discount_band"


@dataclass(frozen=True)
class BandEstimate:
    band: str
    p_purchase: float           # Aito's `$p` that the product is bought when shown
    vs_no_discount: float       # p_purchase / p_purchase at "none"
    band_lift: float | None     # the band's lift in `$why`; None when Aito leaves it out
    product_lift: float | None  # the product's own lift in `$why`
    base_p: float               # the purchase rate of all impressions
    normaliser: float           # Aito's normalisers, multiplied (exclusiveness, calibration)
    calibrated: bool            # `$why` holds a `calibration` factor (Aito's rowCap floor)
    shown: int                  # impressions of this product at this band
    purchased: int              # ... of which bought
    current: bool               # the product's band in the latest month


@dataclass(frozen=True)
class DiscountWhatIf:
    sku: str
    name: str
    current_band: str
    month: str
    bands: list[BandEstimate]
    last_query: dict

    def to_dict(self) -> dict:
        return asdict(self)


def predict_body(sku: str, band: str) -> dict:
    return {"from": "impressions", "where": {"product_sku": sku, BAND_FIELD: band},
            "predict": "purchased", "select": ["$p", "feature", "$why"]}


def get_discount_what_if(client: AitoClient, sku: str) -> DiscountWhatIf:
    products = client.search("products", where={"sku": sku}, limit=1)["hits"]
    if not products:
        raise UnknownProductError(f"No product {sku} in the catalogue")

    counts = [{"from": "impressions", "where": {"product_sku": sku, BAND_FIELD: band, **bought}, "limit": 0}
              for band in BANDS for bought in ({}, {"purchased": True})]
    state = {"from": "product_states", "where": {"product_sku": sku, "month": LATEST_MONTH}, "limit": 1}
    answers = client.batch([*(predict_body(sku, band) for band in BANDS), *counts, state])
    predictions, totals, [state_answer] = answers[:4], answers[4:12], answers[12:]

    if len(state_answer["hits"]) != 1:
        raise AitoError(f"{sku} has {len(state_answer['hits'])} product_states rows for {LATEST_MONTH}")
    current = state_answer["hits"][0]["discount_band"]
    if current not in BANDS:
        raise AitoError(f"{sku} is in discount band {current!r} in {LATEST_MONTH}, not one of {BANDS}")

    estimates = [band_estimate(sku, band, answer) for band, answer in zip(BANDS, predictions)]
    p_none = estimates[0]["p_purchase"]
    bands = [
        BandEstimate(**e, vs_no_discount=e["p_purchase"] / p_none,
                     shown=totals[2 * i]["total"], purchased=totals[2 * i + 1]["total"],
                     current=band == current)
        for i, (band, e) in enumerate(zip(BANDS, estimates))
    ]
    return DiscountWhatIf(sku=sku, name=products[0]["name"], current_band=current, month=LATEST_MONTH,
                          bands=bands, last_query={"endpoint": "_predict", "body": predict_body(sku, current)})


def band_estimate(sku: str, band: str, answer: dict) -> dict:
    """`$p` of the `true` answer and its `$why`, read into one band's row."""
    hit = next((h for h in answer.get("hits", []) if h.get("feature") is True), None)
    if hit is None:
        raise AitoError(f"_predict purchased for {sku} at {band} had no `true` hit: {str(answer)[:300]}")
    why = hit.get("$why")
    if not (isinstance(why, dict) and why.get("type") == "product"):
        raise AitoError(f"_predict purchased for {sku} at {band}: unexpected $why {str(why)[:300]}")

    base_p, normaliser, calibrated, lifts = None, 1.0, False, {}
    for factor in why["factors"]:
        match factor["type"]:
            case "baseP":
                base_p = factor["value"]
            case "product":
                for inner in factor["factors"]:
                    if inner["type"] not in ("normalizer", "calibration"):
                        raise AitoError(f"unexpected factor in $why for {sku} at {band}: {inner}")
                    normaliser *= inner["value"]
                    calibrated = calibrated or inner["type"] == "calibration"
            case "relatedPropositionLift":
                [field] = factor["proposition"]
                lifts[field] = factor["value"]
            case _:
                raise AitoError(f"unexpected factor in $why for {sku} at {band}: {factor}")
    if base_p is None:
        raise AitoError(f"$why for {sku} at {band} has no base rate: {str(why)[:300]}")

    chained = base_p * normaliser * math.prod(lifts.values())
    if not math.isclose(chained, hit["$p"], rel_tol=1e-6):
        raise AitoError(f"$why for {sku} at {band} multiplies to {chained}, but $p is {hit['$p']}")
    return {"band": band, "p_purchase": hit["$p"], "band_lift": lifts.get(BAND_FIELD),
            "product_lift": lifts.get("product_sku"), "base_p": base_p,
            "normaliser": normaliser, "calibrated": calibrated}
