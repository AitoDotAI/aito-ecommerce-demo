"""Offline tests for AitoClient's query methods.

Mocks the HTTP layer with `pytest-httpx` so we can assert the *body
shape* each method emits without needing a live Aito DB. Live
sanity checks live in `./do aito-check` (which lands per view).
"""

from __future__ import annotations

import pytest
from pytest_httpx import HTTPXMock

from src.aito_client import AitoClient, AitoError
from src.config import Config


@pytest.fixture
def client() -> AitoClient:
    cfg = Config(
        aito_api_url="https://example.aito.app",
        aito_api_key="test-key",
        public_demo=False,
    )
    return AitoClient(cfg)


def _last_body(httpx_mock: HTTPXMock) -> dict:
    return httpx_mock.get_requests()[-1].read() and __import__("json").loads(
        httpx_mock.get_requests()[-1].read()
    )


def test_predict_emits_canonical_body(client, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://example.aito.app/api/v1/_predict",
        method="POST",
        json={"hits": [{"feature": "large-breed", "$p": 0.92}]},
    )
    client.predict(
        table="products",
        where={"name": "Acana Large Breed Adult"},
        predict_field="dietary",
    )
    body = _last_body(httpx_mock)
    assert body["from"] == "products"
    assert body["where"] == {"name": "Acana Large Breed Adult"}
    assert body["predict"] == "dietary"
    # $why with sentinel-tagged highlights is part of the demo's
    # explainability story — every predict call asks for it.
    select = body["select"]
    assert "$p" in select and "feature" in select
    why_node = next(s for s in select if isinstance(s, dict))
    assert why_node["$why"]["highlight"]["posPreTag"] == "«"


def test_recommend_omits_select_when_unset(client, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://example.aito.app/api/v1/_recommend",
        method="POST",
        json={"hits": []},
    )
    client.recommend(
        table="order_lines",
        where={"orders.customer_id": "CUST-00001"},
        recommend_field="product_sku",
        goal={"returned": False},
    )
    body = _last_body(httpx_mock)
    assert body["recommend"] == "product_sku"
    assert body["goal"] == {"returned": False}
    # Default behaviour: leave select absent so Aito returns every
    # column of the linked products table.
    assert "select" not in body


def test_relate_round_trips_relate_field(client, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://example.aito.app/api/v1/_relate",
        method="POST",
        json={"hits": []},
    )
    client.relate(
        table="order_lines",
        where={"category": "dry-food", "pet_type": "dog"},
        relate_field="category",
    )
    body = _last_body(httpx_mock)
    assert body["relate"] == "category"


def test_search_strips_optional_args(client, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://example.aito.app/api/v1/_search",
        method="POST",
        json={"hits": [], "offset": 0, "total": 0},
    )
    client.search(table="products", limit=5)
    body = _last_body(httpx_mock)
    assert body == {"from": "products", "limit": 5, "offset": 0}


def test_search_passes_where_and_order_by(client, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://example.aito.app/api/v1/_search",
        method="POST",
        json={"hits": []},
    )
    client.search(
        table="products",
        where={"name": "food"},
        order_by="price_eur",
        limit=10,
    )
    body = _last_body(httpx_mock)
    assert body["where"] == {"name": "food"}
    assert body["orderBy"] == "price_eur"


def test_evaluate_wraps_body_in_evaluate_key(client, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://example.aito.app/api/v1/_evaluate",
        method="POST",
        json={"accuracy": 0.72, "baseAccuracy": 0.5, "totalCases": 200},
    )
    client.evaluate(
        table="order_lines",
        where={"category": {"$get": "category"}},
        predict_field="returned",
    )
    body = _last_body(httpx_mock)
    # Aito requires both `testSource` (which rows to hold out) AND
    # `evaluate` (the prediction shape). See ADR 0010.
    assert "testSource" in body
    assert body["testSource"]["from"] == "order_lines"
    assert "evaluate" in body
    assert body["evaluate"]["predict"] == "returned"
    assert body["evaluate"]["where"] == {"category": {"$get": "category"}}


def test_non_2xx_raises_aito_error(client, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://example.aito.app/api/v1/_predict",
        method="POST",
        status_code=400,
        text='{"error": "bad query"}',
    )
    with pytest.raises(AitoError) as excinfo:
        client.predict(table="products", where={}, predict_field="dietary")
    assert excinfo.value.status_code == 400
    assert "bad query" in str(excinfo.value)
