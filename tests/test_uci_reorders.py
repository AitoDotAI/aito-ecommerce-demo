"""Business reorders on UCI Online Retail II (ADR 0034), against a mocked Aito.

A real `AitoClient` on env `uci` talks to `pytest-httpx`, so each test
shows the exact query sent and the response shape the service reads.
The live versions run in `./do uci-check`.
"""

from __future__ import annotations

import json

import pytest
from pytest_httpx import HTTPXMock

from src.aito_client import AitoClient
from src.config import Config
from src.uci_bought_together import bought_together
from src.uci_buyers import pick_buyers
from src.uci_outcomes import BuyerOutcome, NextOrder
from src.uci_products import UnknownStockCodeError
from src.uci_reorder_service import UnknownBuyerError, draft_order

API = "https://example.aito.app/env/uci/api/v2"

OUTCOMES = {
    "13085": BuyerOutcome("13085", prior_invoices=2,
                          next_order=NextOrder("575000", "2011-11-08", frozenset({"85123A", "22423"}))),
}


@pytest.fixture
def client() -> AitoClient:
    return AitoClient(Config(aito_api_url="https://example.aito.app", aito_api_key="test-key",
                             public_demo=False, use_v2=True, aito_env="uci"))


@pytest.fixture(autouse=True)
def outcomes(monkeypatch):
    monkeypatch.setattr("src.uci_reorder_service.load_outcomes", lambda: OUTCOMES)


def sent(httpx_mock: HTTPXMock, endpoint: str) -> dict:
    return next(json.loads(r.read()) for r in httpx_mock.get_requests() if r.url.path.endswith(endpoint))


def products_response(*rows) -> dict:
    return {"offset": 0, "total": len(rows), "hits": [
        {"code": code, "description": description, "last_price_gbp": price} for code, description, price in rows]}


def mock_draft(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=f"{API}/_predict", method="POST", json={"offset": 0, "total": 4415, "hits": [
        {"$p": 0.21, "$value": "85123A"},
        {"$p": 0.12, "$value": "POST"},
    ]})
    httpx_mock.add_response(url=f"{API}/_search", method="POST", json=products_response(
        ("85123A", "WHITE HANGING HEART T-LIGHT HOLDER", 2.95), ("POST", "POSTAGE", 18.0)))


# ── The draft order: one `_predict`, the benchmark's query ────────


def test_the_draft_is_the_benchmarks_predict_over_the_buyers_lines(client, httpx_mock):
    mock_draft(httpx_mock)

    draft = draft_order(client, "13085")

    expected = {"from": "lines", "where": {"invoice.customer_id": "13085"},
                "predict": "code", "limit": 10, "select": ["$p", "$value"]}
    assert sent(httpx_mock, "/_predict") == expected
    assert draft.query == expected     # the panel shows the body actually sent


def test_each_drafted_code_gets_its_description_and_last_price_from_products(client, httpx_mock):
    mock_draft(httpx_mock)

    draft = draft_order(client, "13085")

    assert sent(httpx_mock, "/_search")["where"] == {"code": {"$or": ["85123A", "POST"]}}
    assert [(line.code, line.description, line.probability, line.last_price_gbp) for line in draft.lines] == [
        ("85123A", "WHITE HANGING HEART T-LIGHT HOLDER", 0.21, 2.95), ("POST", "POSTAGE", 0.12, 18.0)]


def test_drafted_codes_in_the_buyers_next_order_are_marked(client, httpx_mock):
    mock_draft(httpx_mock)

    draft = draft_order(client, "13085")

    assert [line.ordered_next for line in draft.lines] == [True, False]
    assert draft.top_suggestion_ordered       # the benchmark's hit@1 for this buyer
    assert (draft.next_order_date, draft.next_order_size) == ("2011-11-08", 2)


def test_the_drafts_value_is_one_of_each_at_last_prices(client, httpx_mock):
    mock_draft(httpx_mock)

    assert draft_order(client, "13085").draft_value_gbp == 20.95


def test_an_unknown_customer_raises_before_asking_aito(client):
    with pytest.raises(UnknownBuyerError, match="99999"):
        draft_order(client, "99999")


# ── The buyer list ────────────────────────────────────────────────


def outcome(customer_id: str, prior_invoices: int, returns: bool = True) -> BuyerOutcome:
    next_order = NextOrder("580000", "2011-10-01", frozenset({"POST"})) if returns else None
    return BuyerOutcome(customer_id, prior_invoices, next_order)


def test_buyers_are_the_first_by_id_with_few_or_many_orders_and_a_next_order():
    priors = [1, 3, 2, 6, 1, 9, 2, 1, 7, 6]
    outcomes = {f"{10000 + i}": outcome(f"{10000 + i}", p) for i, p in enumerate(priors)}
    outcomes["10000"] = outcome("10000", 1, returns=False)    # never ordered again: left out

    picked = [(b.customer_id, b.group) for b in pick_buyers(outcomes)]

    assert picked == [("10002", "1-2 earlier orders"), ("10004", "1-2 earlier orders"),
                      ("10006", "1-2 earlier orders"), ("10007", "1-2 earlier orders"),
                      ("10003", "regular buyer"), ("10005", "regular buyer")]


# ── Bought together: `_relate` over the baskets' codes ────────────


def relate_hit(token: str, lift: float, together: int, with_code: int = 500) -> dict:
    return {"related": {"codes": {"$has": token}}, "lift": lift,
            "fs": {"fOnCondition": together, "fCondition": 1200, "f": with_code, "n": 29854}}


def test_bought_together_relates_codes_over_baskets_holding_the_chosen_code(client, httpx_mock):
    httpx_mock.add_response(url=f"{API}/_search", method="POST",
                            json=products_response(("85123A", "WHITE HANGING HEART T-LIGHT HOLDER", 2.95)))
    httpx_mock.add_response(url=f"{API}/_relate", method="POST", json={"offset": 0, "total": 3, "hits": [
        relate_hit("85123A", 24.9, 1200, 1200),      # the code itself
        relate_hit("21733", 3.1, 410),
        relate_hit("23503", 9.0, 4),                 # too few shared invoices to call
        relate_hit("BANK_CHARGES", 4.2, 25),
    ]})
    httpx_mock.add_response(url=f"{API}/_search", method="POST", json=products_response(
        ("BANK CHARGES", "Bank Charges", 15.0), ("21733", "RED HANGING HEART T-LIGHT HOLDER", 2.95)))

    result = bought_together(client, "85123A")

    assert sent(httpx_mock, "/_relate") == {"from": "baskets", "where": {"codes": {"$match": "85123A"}},
                                            "relate": ["codes"], "limit": 50}
    assert [(b.code, b.lift, b.shared_invoices) for b in result.bought_with] == [
        ("BANK CHARGES", 4.2, 25), ("21733", 3.1, 410)]
    assert result.invoices_with_product == 1200


def test_bought_together_for_an_unknown_code_raises(client, httpx_mock):
    httpx_mock.add_response(url=f"{API}/_search", method="POST", json=products_response())

    with pytest.raises(UnknownStockCodeError, match="NOPE"):
        bought_together(client, "NOPE")
