"""Discount what-if (ADR 0032): how likely a shown product is bought at
each discount band.

The band is evidence through the impression's `product_state` link:

    POST /_predict
    {"from": "impressions",
     "where": {"product_sku": "SKU-PT-0143", "product_state.discount_band": "20+"},
     "predict": "purchased", "select": ["$p", "feature", "$why"]}

The answers below are what env `observable` returned for SKU-PT-0143 on
2026-10-24 (values rounded), wrapped as v2's `_batch` answers them.
"""

import json
import math

import pytest
from pytest_httpx import HTTPXMock

from src.aito_client import AitoClient, AitoError
from src.config import Config
from src.discount_what_if import BANDS, get_discount_what_if
from src.lookup_errors import UnknownProductError

SKU = "SKU-PT-0143"
API = "https://example.aito.app/api/v2"
BASE_P = 0.1241
PRODUCT_LIFT = 1.4477
BAND_LIFTS = {"none": 0.8751, "10-15": 1.5730, "15-20": 1.6450, "20+": 1.5877}
EXCLUSIVENESS = 0.9662
# The product's impressions at each band: (shown, bought).
SEEN = {"none": (317, 54), "10-15": (28, 7), "15-20": (4, 1), "20+": (29, 7)}


@pytest.fixture
def client() -> AitoClient:
    return AitoClient(Config(aito_api_url="https://example.aito.app", aito_api_key="test-key",
                             public_demo=False, use_v2=True, aito_env="master"))


def prediction(band_lift: float | None, *, calibration: float | None = None) -> dict:
    """One `_predict purchased` answer: the `true` hit's `$why` is the base rate
    × normalisers × one lift per fact, and `$p` is exactly that product."""
    normalisers = [{"type": "normalizer", "name": "exclusiveness", "value": EXCLUSIVENESS}]
    if calibration is not None:
        normalisers.append({"type": "calibration", "name": "rowCap", "value": calibration})
    lifts = [{"type": "relatedPropositionLift", "proposition": {"product_sku": SKU}, "value": PRODUCT_LIFT}]
    if band_lift is not None:
        lifts.append({"type": "relatedPropositionLift",
                      "proposition": {"product_state.discount_band": "x"}, "value": band_lift})
    p = BASE_P * math.prod(n["value"] for n in normalisers) * math.prod(f["value"] for f in lifts)
    why = {"type": "product", "factors": [
        {"type": "baseP", "value": BASE_P, "proposition": {"purchased": {"$has": True}}},
        {"type": "product", "factors": normalisers}, *lifts]}
    return {"kind": "rows", "total": 2, "hits": [
        {"$p": 1 - p, "feature": False}, {"$p": p, "feature": True, "$why": why}]}


def batch_answer(predictions: list[dict], current_band: str = "none") -> dict:
    counts = [{"kind": "rows", "total": n, "hits": []} for band in BANDS for n in SEEN[band]]
    state = {"kind": "rows", "total": 1, "hits": [{"product_sku": SKU, "month": "2026-04",
                                                   "discount_band": current_band}]}
    return {"kind": "batch", "data": [*predictions, *counts, state]}


def mock_aito(httpx_mock: HTTPXMock, predictions=None, current_band="none", products=True):
    httpx_mock.add_response(url=f"{API}/_search", method="POST", json={"hits": [
        {"sku": SKU, "name": "PetNord Dental Chews"}] if products else []})
    if products:
        predictions = predictions or [prediction(BAND_LIFTS[band]) for band in BANDS]
        httpx_mock.add_response(url=f"{API}/_batch", method="POST",
                                json=batch_answer(predictions, current_band))


def test_one_batch_asks_each_band_with_the_product_and_counts_what_was_seen(client, httpx_mock):
    mock_aito(httpx_mock)

    get_discount_what_if(client, SKU)

    queries = json.loads(httpx_mock.get_requests()[-1].read())
    predicts = [q for q in queries if q.get("predict") == "purchased"]
    assert [q["where"] for q in predicts] == [
        {"product_sku": SKU, "product_state.discount_band": band} for band in BANDS]
    assert all(q["from"] == "impressions" and "$why" in q["select"] for q in predicts)
    # Then shown and bought per band, and the product's state this month.
    assert queries[5]["where"] == {"product_sku": SKU, "product_state.discount_band": "none", "purchased": True}
    assert queries[-1]["where"] == {"product_sku": SKU, "month": "2026-04"}


def test_each_band_reads_aitos_estimate_its_lift_and_what_was_seen(client, httpx_mock):
    mock_aito(httpx_mock, current_band="20+")

    result = get_discount_what_if(client, SKU)

    top = result.bands[3]
    assert (top.band, top.current, top.shown, top.purchased) == ("20+", True, 29, 7)
    assert top.p_purchase == pytest.approx(BASE_P * EXCLUSIVENESS * PRODUCT_LIFT * 1.5877)
    assert (top.band_lift, top.product_lift, top.base_p) == (1.5877, PRODUCT_LIFT, BASE_P)
    assert result.current_band == "20+" and [b.current for b in result.bands] == [False, False, False, True]


def test_a_discount_reads_against_no_discount_as_the_ratio_of_the_two_estimates(client, httpx_mock):
    mock_aito(httpx_mock)

    bands = get_discount_what_if(client, SKU).bands

    assert bands[0].vs_no_discount == 1.0
    assert bands[1].vs_no_discount == pytest.approx(1.5730 / 0.8751)


def test_the_aito_panel_shows_the_query_for_the_current_band(client, httpx_mock):
    mock_aito(httpx_mock, current_band="10-15")

    query = get_discount_what_if(client, SKU).last_query

    assert query["endpoint"] == "_predict"
    assert query["body"]["where"] == {"product_sku": SKU, "product_state.discount_band": "10-15"}


def test_a_band_aito_leaves_out_of_why_has_no_lift_rather_than_a_made_up_one(client, httpx_mock):
    # A product only ever shown undiscounted: "none" is implied by the product.
    mock_aito(httpx_mock, predictions=[prediction(None), *(prediction(BAND_LIFTS[b]) for b in BANDS[1:])])

    assert get_discount_what_if(client, SKU).bands[0].band_lift is None


def test_aitos_calibration_floor_is_flagged_and_kept_in_the_chain(client, httpx_mock):
    # A product nobody buys: `$why` gains `calibration: rowCap`, and `$p` sits at a floor.
    mock_aito(httpx_mock, predictions=[prediction(BAND_LIFTS[b], calibration=1.2407) for b in BANDS])

    none = get_discount_what_if(client, SKU).bands[0]

    assert none.calibrated
    assert none.normaliser == pytest.approx(EXCLUSIVENESS * 1.2407)


def test_a_why_that_does_not_multiply_out_to_p_raises(client, httpx_mock):
    broken = prediction(BAND_LIFTS["none"])
    broken["hits"][1]["$p"] *= 1.5
    mock_aito(httpx_mock, predictions=[broken, *(prediction(BAND_LIFTS[b]) for b in BANDS[1:])])

    with pytest.raises(AitoError, match="multiplies to"):
        get_discount_what_if(client, SKU)


def test_an_unknown_product_is_refused(client, httpx_mock):
    mock_aito(httpx_mock, products=False)

    with pytest.raises(UnknownProductError):
        get_discount_what_if(client, "NOPE-1")


def test_the_current_band_is_the_one_in_the_month_asked_about(client, httpx_mock):
    # The Product view opens on any month; the estimates don't change with it.
    mock_aito(httpx_mock, current_band="15-20")

    result = get_discount_what_if(client, SKU, "2025-11")

    queries = json.loads(httpx_mock.get_requests()[-1].read())
    assert queries[-1]["where"] == {"product_sku": SKU, "month": "2025-11"}
    assert (result.month, result.current_band) == ("2025-11", "15-20")
