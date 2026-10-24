"""The Aito method of the reorder backtest (ADR 0036), against a mocked Aito.

A real `AitoClient` on env `uci` talks to `pytest-httpx`, so each test
shows the exact `_predict` sent per buyer and the response read back.
The live run is `AITO_ENV=uci ./do backtest uci`.
"""

from __future__ import annotations

import json

import httpx
import pytest
from pytest_httpx import HTTPXMock

from src.aito_client import AitoClient, AitoError
from src.backtest_aito import aito_rankings, explain_top_suggestion, require_dataset_env
from src.backtest_dataset import BacktestDataset, HeldOutOrder, TrainOrder
from src.backtest_metrics import AITO
from src.backtest_run import run_backtest
from src.config import Config

PREDICT = "https://example.aito.app/env/uci/api/v2/_predict"

# A `$why` tree in the shape `src/why_processor.py` reads on v2: a baseP,
# a normaliser (dropped) and a lift whose proposition is a bare
# `{field: value}`. To be checked against env `uci` on the live run.
WHY = {"type": "product", "factors": [
    {"type": "baseP", "value": 0.012, "proposition": {"code": "85123A"}},
    {"type": "normalizer", "name": "exclusiveness", "value": 0.9},
    {"type": "relatedPropositionLift", "value": 8.4, "proposition": {"invoice.customer_id": "13085"}},
]}


@pytest.fixture
def client() -> AitoClient:
    return AitoClient(Config(aito_api_url="https://example.aito.app", aito_api_key="test-key",
                             public_demo=False, use_v2=True, aito_env="uci"))


def fake_aito(httpx_mock: HTTPXMock, top_codes: dict[str, list[str]]) -> None:
    """Answer each buyer's `_predict` with their codes; a `$why` request gets the tree too."""
    def answer(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.read())
        codes = top_codes[body["where"]["invoice.customer_id"]][:body["limit"]]
        hits = [{"$p": 0.2 - 0.01 * i, "$value": code} for i, code in enumerate(codes)]
        if {"$why": {}} in body["select"]:
            hits = [{**hit, "$why": WHY} for hit in hits]
        return httpx.Response(200, json={"offset": 0, "total": 4415, "hits": hits})
    httpx_mock.add_callback(answer, url=PREDICT, method="POST", is_reusable=True)


def sent_bodies(httpx_mock: HTTPXMock) -> list[dict]:
    return [json.loads(r.read()) for r in httpx_mock.get_requests()]


def test_each_buyer_is_ranked_by_adr_0034s_predict_unchanged(client, httpx_mock):
    fake_aito(httpx_mock, {"13085": ["85123A", "POST"], "12357": ["22423"]})

    rankings = aito_rankings(client, ["12357", "13085"])

    assert rankings == {"12357": ["22423"], "13085": ["85123A", "POST"]}
    assert sent_bodies(httpx_mock)[1] == {"from": "lines", "where": {"invoice.customer_id": "13085"},
                                          "predict": "code", "limit": 10, "select": ["$p", "$value"]}


def test_the_why_comes_from_a_separate_query_so_the_measured_one_stays_the_benchmarks(client, httpx_mock):
    fake_aito(httpx_mock, {"13085": ["85123A", "POST"]})

    why = explain_top_suggestion(client, "13085", "85123A")

    assert sent_bodies(httpx_mock) == [{"from": "lines", "where": {"invoice.customer_id": "13085"},
                                        "predict": "code", "limit": 1, "select": ["$p", "$value", {"$why": {}}]}]
    assert why == "base 1.2%; ×8.40 when invoice.customer_id is 13085; p 20.0%"


def test_a_why_query_that_ranks_another_code_first_fails_loudly(client, httpx_mock):
    fake_aito(httpx_mock, {"13085": ["POST"]})

    with pytest.raises(AitoError, match="must agree"):
        explain_top_suggestion(client, "13085", "85123A")


def test_the_aito_method_runs_only_against_the_datasets_own_env(client):
    with pytest.raises(SystemExit, match="backtest-acme"):
        require_dataset_env(client, "acme", "uci")
    require_dataset_env(client, "uci", "uci")


def test_a_run_with_aito_scores_it_beside_the_baselines_and_explains_ten_example_buyers(client, httpx_mock):
    train = [TrainOrder("i1", "13085", "2011-05", ("85123A", "POST")),
             TrainOrder("i2", "12357", "2011-06", ("22423",))]
    tests = {"13085": HeldOutOrder("t1", "2011-09-05", frozenset({"85123A"})),
             "12357": HeldOutOrder("t2", "2011-10-01", frozenset({"POST"}))}
    dataset = BacktestDataset("uci", "test", "2011-09-01", train, tests)
    fake_aito(httpx_mock, {"13085": ["85123A", "POST"], "12357": ["22423", "POST"]})

    run = run_backtest(dataset, client)

    (_, few, _) = run.slices
    assert few.buyers == 2 and few.hit1[AITO].mean == 0.5
    assert [(e.customer_id, e.top_code, e.hit) for e in sorted(run.examples, key=lambda e: e.customer_id)] == [
        ("12357", "22423", False), ("13085", "85123A", True)]
