"""Product KPIs by properties (ADR 0048): `_predict clicked|purchased` on impressions with the product's
properties, through the `product_sku` and `product_state` links, in the `where`.

    POST /_predict
    {"from": "impressions",
     "where": {"product_sku.brand": "PetNord", "product_sku.category": "treats", "product_sku.pet_type": "dog",
               "product_state.discount_band": "15-20", ...},
     "predict": "clicked", "select": ["$p", "feature", "$why"]}

The `$why` below has the shape env `master` returned on 2026-10-26 (values rounded): the base rate, one
nested product of normalisers, a lift per property and one lift for a group of correlated ones.
"""

import json
import math

import pytest
from pytest_httpx import HTTPXMock

from src.aito_client import AitoClient, AitoError
from src.config import Config
from src.lookup_errors import UnknownProductError
from src.product_kpi import get_product_kpis

SKU = "SKU-PT-0143"
API = "https://example.aito.app/api/v2"
PRODUCT = {"sku": SKU, "name": "PetNord Bacon Treats 200g", "brand": "PetNord", "category": "treats", "pet_type": "dog"}
STATE = {"product_sku": SKU, "month": "2026-04", "discount_band": "none", "rating_band": "4", "label": "none",
         "age": "established", "stock": "in_stock", "rival_launched": False,
         "list_price_eur": 10.0, "list_price_index": 1.0, "image_count": "2-3", "description_quality": "ok",
         "ad_level": "none"}


# A refused or unknown request stops before the batch, which the mock still offers.
pytestmark = pytest.mark.httpx_mock(assert_all_responses_were_requested=False)


@pytest.fixture
def client() -> AitoClient:
    return AitoClient(Config(aito_api_url="https://example.aito.app", aito_api_key="test-key",
                             public_demo=False, use_v2=True, aito_env="master"))


def prediction(base_p: float, band_lift: float, *, broken: bool = False) -> dict:
    lifts = [
        {"type": "relatedPropositionLift", "proposition": {"product_sku.category": "treats"}, "value": 1.2},
        {"type": "relatedPropositionLift", "proposition": {"product_state.discount_band": "none"}, "value": band_lift},
        {"type": "relatedPropositionLift",
         "proposition": {"$group": [{"product_state.label": "none"}, {"product_state.age": "established"}]}, "value": 0.95},
    ]
    normalisers = [{"type": "normalizer", "name": "exclusiveness", "value": 0.97},
                   {"type": "normalizer", "name": "trueFalseExclusiveness", "value": 1.0}]
    p = base_p * 0.97 * math.prod(f["value"] for f in lifts) * (1.5 if broken else 1)
    why = {"type": "product", "factors": [
        {"type": "baseP", "value": base_p, "proposition": {"x": {"$has": True}}},
        {"type": "product", "factors": normalisers}, *lifts]}
    return {"kind": "rows", "total": 2, "hits": [{"$p": 1 - p, "feature": False}, {"$p": p, "feature": True, "$why": why}]}


def counts(*totals: int) -> list[dict]:
    return [{"kind": "rows", "total": n, "hits": []} for n in totals]


def mock_aito(httpx_mock: HTTPXMock, *, predictions=None, product=True, state=True):
    for hits in ([PRODUCT] if product else [], [STATE] if state else []):    # the product, then its state
        httpx_mock.add_response(url=f"{API}/_search", method="POST", json={"hits": hits})
    httpx_mock.add_response(url=f"{API}/_batch", method="POST", json={"kind": "batch", "data": [
        *(predictions or [prediction(0.31, 0.87), prediction(0.14, 0.78)]),
        # properties' showings, clicked, bought; then the product's own
        *counts(183, 86, 42, 160, 60, 39)]})


def test_the_query_has_the_products_properties_not_its_sku(client, httpx_mock):
    mock_aito(httpx_mock)

    get_product_kpis(client, SKU, "2026-04", {})

    queries = json.loads(httpx_mock.get_requests()[-1].read())
    assert [q["predict"] for q in queries[:2]] == ["clicked", "purchased"]
    assert queries[0]["where"] == {
        "product_sku.brand": "PetNord", "product_sku.category": "treats", "product_sku.pet_type": "dog",
        "product_state.discount_band": "none", "product_state.rating_band": "4", "product_state.label": "none",
        "product_state.age": "established", "product_state.stock": "in_stock", "product_state.rival_launched": False,
        "product_state.list_price_index": 1.0, "product_state.image_count": "2-3",
        "product_state.description_quality": "ok", "product_state.ad_level": "none"}
    assert "product_sku" not in queries[0]["where"] and "$why" in queries[0]["select"]


def test_a_change_replaces_that_property_and_is_listed(client, httpx_mock):
    mock_aito(httpx_mock)

    result = get_product_kpis(client, SKU, "2026-04", {"discount_band": "20+", "rival_launched": True})

    where = json.loads(httpx_mock.get_requests()[-1].read())[0]["where"]
    assert (where["product_state.discount_band"], where["product_state.rival_launched"]) == ("20+", True)
    assert result.changed == ["discount_band", "rival_launched"] and result.properties["discount_band"] == "20+"


def test_a_new_list_price_in_euros_becomes_the_list_price_index_the_data_holds(client, httpx_mock):
    mock_aito(httpx_mock)

    result = get_product_kpis(client, SKU, "2026-04", {"list_price_eur": 9.0})

    where = json.loads(httpx_mock.get_requests()[-1].read())[0]["where"]
    assert where["product_state.list_price_index"] == 0.9      # against a reference list price of €10.00
    assert result.changed == ["list_price_index"]


def test_a_property_that_is_not_editable_is_refused(client, httpx_mock):
    mock_aito(httpx_mock)

    with pytest.raises(ValueError, match="Not an editable property"):
        get_product_kpis(client, SKU, "2026-04", {"brand": "Acme"})


def test_each_kpi_reads_p_the_base_rate_and_a_lift_per_property(client, httpx_mock):
    mock_aito(httpx_mock)

    clicked = get_product_kpis(client, SKU, "2026-04", {}).estimates["clicked"]

    assert clicked.p == pytest.approx(0.31 * 0.97 * 1.2 * 0.87 * 0.95)
    assert (clicked.base_p, clicked.normaliser) == (0.31, pytest.approx(0.97))
    assert [(f.fields, f.lift) for f in clicked.factors] == [
        (["category"], 1.2), (["discount_band"], 0.87), (["label", "age"], 0.95)]   # a group is one lift


def test_what_actually_happened_sits_beside_the_estimate(client, httpx_mock):
    mock_aito(httpx_mock)

    estimates = get_product_kpis(client, SKU, "2026-04", {}).estimates

    assert (estimates["clicked"].similar_shown, estimates["clicked"].similar_hits) == (183, 86)
    assert (estimates["purchased"].similar_hits, estimates["purchased"].product_shown, estimates["purchased"].product_hits) == (42, 160, 39)


def test_an_unknown_product_or_a_month_it_was_not_on_sale_is_named(client, httpx_mock):
    mock_aito(httpx_mock, product=False)
    with pytest.raises(UnknownProductError, match="No product"):
        get_product_kpis(client, SKU, "2026-04", {})


def test_a_month_without_a_state_is_named(client, httpx_mock):
    mock_aito(httpx_mock, state=False)
    with pytest.raises(UnknownProductError, match="no state in 2026-04"):
        get_product_kpis(client, SKU, "2026-04", {})


def test_a_why_that_does_not_multiply_out_to_p_raises(client, httpx_mock):
    mock_aito(httpx_mock, predictions=[prediction(0.31, 0.87, broken=True), prediction(0.14, 0.78)])

    with pytest.raises(AitoError, match="multiplies to"):
        get_product_kpis(client, SKU, "2026-04", {})
