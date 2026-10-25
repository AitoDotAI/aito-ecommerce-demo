"""Ask the store's routes: off without a key and an admin token, 403 without the token, errors mapped."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src import ask_routes
from src.aito_client import AitoError
from src.ask_routes import router
from src.ask_store import Answer, AskError

TOKEN = "s3cret-admin-token"


class Demo:
    def reader(self, request):
        return object()


def client() -> TestClient:
    api = FastAPI()
    api.include_router(router)
    api.state.demo_clients = Demo()
    api.state.ask_supply = dict
    api.state.ask_retention = dict
    return TestClient(api)


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("ADMIN_TOKEN", TOKEN)
    monkeypatch.setattr(ask_routes.anthropic, "Anthropic", lambda: object())


def test_without_a_key_ask_is_off_and_answers_404(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("ADMIN_TOKEN", TOKEN)

    assert client().get("/api/ask").json() == {"enabled": False, "model": None}
    assert client().post("/api/ask", json={"question": "What next?"}, headers={"X-Admin-Token": TOKEN}).status_code == 404


def test_without_an_admin_token_ask_is_off_even_with_a_key(key, monkeypatch):
    monkeypatch.delenv("ADMIN_TOKEN")

    assert client().get("/api/ask").json()["enabled"] is False


def test_with_a_key_and_a_token_the_status_names_the_model(key):
    assert client().get("/api/ask").json() == {"enabled": True, "model": "claude-opus-5-5"}


@pytest.mark.parametrize("given", ["", "wrong", TOKEN + "x"])
def test_a_question_with_a_wrong_token_is_403(key, given):
    response = client().post("/api/ask", json={"question": "What next?"}, headers={"X-Admin-Token": given})

    assert response.status_code == 403


def test_a_question_is_answered_with_the_tool_calls_beside_it(key, monkeypatch):
    monkeypatch.setattr(ask_routes, "ask", lambda question, tools, claude, model: Answer(f"re: {question}", [], model, 1, 2))

    response = client().post("/api/ask", json={"question": "What next?"}, headers={"X-Admin-Token": TOKEN})

    assert response.status_code == 200 and response.json()["answer"] == "re: What next?"


@pytest.mark.parametrize("error, status", [(AskError("The model declined this question."), 422), (AitoError("boom", 500), 502)])
def test_failures_are_mapped_to_a_status_with_the_message(key, monkeypatch, error, status):
    def failing(question, tools, claude, model):
        raise error
    monkeypatch.setattr(ask_routes, "ask", failing)

    response = client().post("/api/ask", json={"question": "What next?"}, headers={"X-Admin-Token": TOKEN})

    assert response.status_code == status and error.args[0] in response.json()["error"]


def test_a_question_too_short_or_too_long_is_422(key):
    for question in ("?", "x" * 501):
        assert client().post("/api/ask", json={"question": question}, headers={"X-Admin-Token": TOKEN}).status_code == 422
