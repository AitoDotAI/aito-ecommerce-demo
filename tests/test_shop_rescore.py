"""The Shop in a sandbox's 2026-05, re-scored by the levers (ADR 0043).

    score = $p (the Shop's _recommend) × offer factor × star factor

The factors are Aito's shop-wide lifts, read from `$why` of one
`_predict purchased` per band (values as env `observable` answered them,
2026-10-24): an offer band against no offer, a star band against April's.
"""

import pytest
from pytest_httpx import HTTPXMock

from src.aito_client import AitoClient, AitoError
from src.config import Config
from src.shop_ranking import ShopItem
from src.shop_rescore import rescore
from src.shop_state_lifts import RATING_BANDS, band_lift, read_state_lifts
from src.discount_what_if import BANDS
from tests.fake_sandbox_aito import BRANCH, BRANCH_API, SANDBOX_URL, april_state

DISCOUNT_LIFTS = {"none": 0.8748, "10-15": 1.5727, "15-20": 1.6450, "20+": 1.5877}
RATING_LIFTS = {"unrated": 0.8131, "1-2": 0.6991, "3": 0.9932, "4": 1.1981, "5": 1.2708}


@pytest.fixture
def client() -> AitoClient:
    return AitoClient(Config(aito_api_url=SANDBOX_URL, aito_api_key="rw", public_demo=False,
                             use_v2=True, aito_env=BRANCH))


def lift_answer(field: str, band: str, lift: float) -> dict:
    why = {"type": "product", "factors": [
        {"type": "baseP", "value": 0.1241, "proposition": {"purchased": {"$has": True}}},
        {"type": "product", "factors": [{"type": "normalizer", "name": "exclusiveness", "value": 1.0}]},
        {"type": "relatedPropositionLift", "proposition": {field: band}, "value": lift}]}
    return {"hits": [{"$p": 0.1241 * lift, "feature": True, "$why": why}, {"$p": 1 - 0.1241 * lift, "feature": False}]}


def lifts_batch() -> dict:
    answers = ([lift_answer("product_state.discount_band", b, DISCOUNT_LIFTS[b]) for b in BANDS]
               + [lift_answer("product_state.rating_band", b, RATING_LIFTS[b]) for b in RATING_BANDS])
    return {"kind": "batch", "data": answers}


def item(sku: str, p: float) -> ShopItem:
    return ShopItem(sku=sku, name=sku, brand="Trixie", pet_type="small_animal", category="accessories",
                    price_eur=20.0, p=p, reasons=[], avg_rating=None, offer_pct=None, keeps_rule=False)


def mock(httpx_mock: HTTPXMock, may_states: list[dict], april: list[dict]) -> None:
    httpx_mock.add_response(url=f"{BRANCH_API}/_search", match_json={
        "from": "product_states", "limit": 3, "offset": 0,
        "where": {"month": "2026-05", "product_sku": {"$or": ["A", "B", "C"]}}},
        json={"total": len(may_states), "hits": may_states})
    if may_states:
        httpx_mock.add_response(url=f"{BRANCH_API}/_search", json={"total": len(april), "hits": april})
        httpx_mock.add_response(url=f"{BRANCH_API}/_batch", json=lifts_batch())


def may(sku: str, band: str, rating_band: str) -> dict:
    return {**april_state(sku), "month": "2026-05", "discount_band": band, "rating_band": rating_band}


def test_the_lifts_are_read_from_why_once_per_page_in_one_batch(client, httpx_mock):
    httpx_mock.add_response(url=f"{BRANCH_API}/_batch", json=lifts_batch())

    lifts = read_state_lifts(client)

    assert lifts.offer_factor("20+") == pytest.approx(1.5877 / 0.8748)     # ×1.81, "On offer"
    assert lifts.rating_factor("3", before="4") == pytest.approx(0.9932 / 1.1981)
    assert len(httpx_mock.get_requests()) == 1


def test_an_offer_lifts_the_product_up_the_grid_and_its_explanation_multiplies_out(client, httpx_mock):
    mock(httpx_mock, [may("C", "20+", "4")], [april_state("C", rating_band="4")])

    ranked = rescore(client, [item("A", 0.40), item("B", 0.30), item("C", 0.26)], "2026-05")

    assert [i.sku for i in ranked] == ["C", "A", "B"]
    c = ranked[0]
    assert (c.measured_rank, c.p) == (3, 0.26)    # Aito's own number is kept, not overwritten
    a = c.adjustment
    assert a.score == pytest.approx(a.aito_p * a.offer_factor * a.rating_factor)
    assert (a.offer_factor, a.rating_factor) == (pytest.approx(1.815, abs=1e-3), 1.0)
    assert ranked[1].adjustment is None and ranked[1].measured_rank == 1


def test_a_star_band_that_fell_lowers_the_score_by_the_bands_lift(client, httpx_mock):
    mock(httpx_mock, [may("A", "none", "3")], [april_state("A", rating_band="4")])

    ranked = rescore(client, [item("A", 0.40), item("B", 0.35), item("C", 0.10)], "2026-05")

    a = next(i for i in ranked if i.sku == "A").adjustment
    assert a.score == pytest.approx(0.40 * (0.9932 / 1.1981))     # 0.33: below B now
    assert [i.sku for i in ranked] == ["B", "A", "C"]


def test_without_any_lever_the_measured_ranking_stands_and_no_lift_is_asked(client, httpx_mock):
    mock(httpx_mock, [], [])

    ranked = rescore(client, [item("A", 0.40), item("B", 0.30), item("C", 0.26)], "2026-05")

    assert [(i.sku, i.measured_rank, i.adjustment) for i in ranked] == [("A", 1, None), ("B", 2, None), ("C", 3, None)]


def test_only_the_sandboxes_month_is_re_scored(client):
    with pytest.raises(ValueError, match="2026-05"):
        rescore(client, [item("A", 0.4)], "2026-04")


def test_a_band_missing_from_why_raises_rather_than_guessing_a_lift():
    answer = lift_answer("product_state.rating_band", "4", 1.2)
    answer["hits"][0]["$why"]["factors"].pop()

    with pytest.raises(AitoError, match="0 lifts of the band"):
        band_lift("product_state.rating_band", "4", answer)

