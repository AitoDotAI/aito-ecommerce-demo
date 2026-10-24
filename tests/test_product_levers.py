"""The owner's levers (ADR 0043): an offer and a review, written to the
sandbox branch's next month, 2026-05, and read back.

Every write is one v2 `POST /data/_modify`:

    {"into": "product_states", "insert": {...May's row...}}                 the first lever
    {"update": "product_states", "set": {...}, "where": {"product_state_id": "SKU-…-2026-05"}}   later ones
    {"into": "reviews", "insert": {...one review...}}

then `_search` reads the row back, and only what was read is returned.
"""

import pytest
from pytest_httpx import HTTPXMock

from src.aito_client import AitoClient, AitoError
from src.config import Config
from src.lookup_errors import UnknownProductError
from src.product_levers import LeverInputError, add_review, set_offer
from tests.fake_sandbox_aito import BRANCH, BRANCH_API, SANDBOX_URL, FakeBranch, april_state, review

SKU = "SKU-PT-0563"     # Trixie Hideout: the next item for Päivi's guinea-pig kit


@pytest.fixture
def branch_client() -> AitoClient:
    return AitoClient(Config(aito_api_url=SANDBOX_URL, aito_api_key="sandbox-rw", public_demo=False,
                             use_v2=True, aito_env=BRANCH))


def fake(httpx_mock: HTTPXMock, *, ratings=(4, 4, 4, 4, 3, 4), rating_band="4") -> FakeBranch:
    branch = FakeBranch([april_state(SKU, rating_band=rating_band)],
                        [review(SKU, i, r) for i, r in enumerate(ratings)])
    httpx_mock.add_callback(branch, is_reusable=True)
    return branch


def test_an_offer_writes_mays_state_at_the_bands_price_and_returns_it_as_read_back(branch_client, httpx_mock):
    branch = fake(httpx_mock)

    result = set_offer(branch_client, SKU, "20+")

    assert result.state["product_state_id"] == f"{SKU}-2026-05"
    assert (result.state["discount_band"], result.state["on_offer"]) == ("20+", True)
    # April's list price €20.00 at the band's typical 22.5 % off.
    assert (result.state["price_eur"], result.state["list_price_eur"], result.state["discount_pct"]) == (15.5, 20.0, 22.5)
    assert branch.tables["product_states"][-1] == result.state


def test_every_write_goes_to_the_branch_never_to_a_master(branch_client, httpx_mock):
    branch = fake(httpx_mock)

    set_offer(branch_client, SKU, "10-15")

    assert branch.writes() == [("POST", f"{BRANCH_API}/data/_modify")]


def test_a_second_offer_updates_mays_row_in_place_rather_than_adding_one(branch_client, httpx_mock):
    branch = fake(httpx_mock)

    set_offer(branch_client, SKU, "20+")
    set_offer(branch_client, SKU, "none")

    first, second = [body for method, url, body in branch.requests if url.endswith("/data/_modify")]
    assert first["into"] == "product_states"
    assert second["update"] == "product_states" and second["where"] == {"product_state_id": f"{SKU}-2026-05"}

    may = [r for r in branch.tables["product_states"] if r["month"] == "2026-05"]
    assert [(r["discount_band"], r["price_eur"]) for r in may] == [("none", 20.0)]


def test_a_one_star_review_that_moves_the_average_below_3_5_lowers_the_star_band(branch_client, httpx_mock):
    # Six reviews averaging 3.83 ("4"); a seventh of 1 star makes 3.43 ("3").
    branch = fake(httpx_mock)

    result = add_review(branch_client, SKU, 1, "Too small for a guinea pig.")

    assert (result.rating_band_before, result.state["rating_band"], result.rating_band_changed) == ("4", "3", True)
    assert (result.reviews, round(result.avg_rating, 2)) == (7, 3.43)
    assert result.review["created_at"] == "2026-05" and result.review["sentiment"] == "negative"
    assert len(branch.tables["reviews"]) == 7


def test_a_review_that_leaves_the_average_in_its_band_reports_no_change(branch_client, httpx_mock):
    fake(httpx_mock, ratings=(1, 2, 1, 2, 2, 2, 1), rating_band="1-2")

    result = add_review(branch_client, SKU, 5, "My guinea pig loves it.")

    assert (result.state["rating_band"], result.rating_band_changed) == ("1-2", False)


def test_a_review_keeps_the_owners_offer_on_mays_state(branch_client, httpx_mock):
    fake(httpx_mock)

    set_offer(branch_client, SKU, "15-20")
    result = add_review(branch_client, SKU, 5, "Great.")

    assert result.state["discount_band"] == "15-20"


def test_a_row_read_back_differently_from_what_was_written_raises(branch_client, httpx_mock):
    branch = fake(httpx_mock)
    original = branch.__call__

    def corrupting(request):
        response = original(request)
        if request.url.path.endswith("/data/_modify"):
            branch.tables["product_states"][-1] = {**branch.tables["product_states"][-1], "price_eur": 99.0}
        return response
    httpx_mock.reset()
    httpx_mock.add_callback(corrupting, is_reusable=True)

    with pytest.raises(AitoError, match="read back differently"):
        set_offer(branch_client, SKU, "20+")


def test_unknown_bands_stars_and_products_are_refused(branch_client, httpx_mock):
    fake(httpx_mock)

    with pytest.raises(LeverInputError):
        set_offer(branch_client, SKU, "50%")
    with pytest.raises(LeverInputError):
        add_review(branch_client, SKU, 6, "Six stars")
    with pytest.raises(UnknownProductError):
        set_offer(branch_client, "SKU-PT-9999", "20+")
