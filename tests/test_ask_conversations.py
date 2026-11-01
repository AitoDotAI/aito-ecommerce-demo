"""Stored Ask conversations (ADR 0054): kept as files, listed and opened without a key, and checked when read."""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src import ask_conversations
from src.shopkeeper_routes import router


@pytest.fixture
def conversations_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(ask_conversations, "DIRECTORY", tmp_path)
    return tmp_path


ANSWER = {
    "answer": "Order 40 units of dog dry food.", "model": "claude-opus-5-5", "input_tokens": 1200, "output_tokens": 300,
    "tool_calls": [{"name": "supply_reorder", "input": {"sku": "S1"}, "ms": 840, "error": None, "result": {"reorder": 40}}],
}


def api() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_a_saved_conversation_is_listed_and_opened_with_its_tool_calls(conversations_dir):
    saved = ask_conversations.save("What should I reorder?", ANSWER, asked_at="2026-11-01T09:30:00Z", release="release3b")

    listed = ask_conversations.list_conversations()
    opened = ask_conversations.load(saved)

    assert [c["id"] for c in listed] == [saved]
    assert listed[0]["question"] == "What should I reorder?" and listed[0]["tool_calls"] == 1
    assert opened["tool_calls"][0]["result"] == {"reorder": 40}
    assert opened["release"] == "release3b"


def test_the_newest_conversation_is_listed_first(conversations_dir):
    older = ask_conversations.save("First?", ANSWER, asked_at="2026-10-31T09:00:00Z", release="r")
    newer = ask_conversations.save("Second?", ANSWER, asked_at="2026-11-01T09:00:00Z", release="r")

    assert [c["id"] for c in ask_conversations.list_conversations()] == [newer, older]


def test_a_stored_file_missing_a_field_fails_loudly_when_read(conversations_dir):
    (conversations_dir / "broken.json").write_text(json.dumps({"id": "broken", "question": "?"}))

    with pytest.raises(ValueError, match="broken.*answer"):
        ask_conversations.load("broken")


@pytest.mark.parametrize("bad", ["../secrets", "a/b", "", "x" * 200])
def test_an_id_that_is_not_a_conversation_id_is_refused(conversations_dir, bad):
    with pytest.raises(ValueError):
        ask_conversations.load(bad)


def test_the_overview_lists_conversations_apart_from_the_win_back_runs(conversations_dir):
    ask_conversations.save("What should I reorder?", ANSWER, asked_at="2026-11-01T09:30:00Z", release="r")

    body = api().get("/api/shopkeeper").json()

    assert [c["question"] for c in body["conversations"]] == ["What should I reorder?"]
    assert [r["id"] for r in body["runs"]] == ["winback"]


def test_a_conversation_opens_by_route_and_an_unknown_one_is_a_404(conversations_dir):
    saved = ask_conversations.save("What should I reorder?", ANSWER, asked_at="2026-11-01T09:30:00Z", release="r")

    assert api().get(f"/api/shopkeeper/conversations/{saved}").json()["answer"] == ANSWER["answer"]
    assert api().get("/api/shopkeeper/conversations/nope").status_code == 404
    assert api().get("/api/shopkeeper/conversations/..%2Fx").status_code in (400, 404)


def test_every_routine_says_whether_it_is_a_rule_or_an_agent():
    routines = api().get("/api/shopkeeper").json()["routines"]

    assert {r["id"]: r["kind"] for r in routines}["winback"] == "rule"
    assert all(r["kind"] in ("rule", "agent") and r["why"] for r in routines)


def test_only_the_predefined_questions_without_a_stored_conversation_are_missing(conversations_dir, monkeypatch):
    monkeypatch.setattr(ask_conversations, "PREDEFINED_QUESTIONS", ("First?", "Second?"))
    ask_conversations.save("First?", ANSWER, asked_at="2026-11-01T09:00:00Z", release="r")

    assert ask_conversations.missing_questions() == ["Second?"]


def test_nothing_is_missing_once_every_predefined_question_is_stored(conversations_dir, monkeypatch):
    monkeypatch.setattr(ask_conversations, "PREDEFINED_QUESTIONS", ("What should I reorder?",))
    ask_conversations.save("What should I reorder?", ANSWER, asked_at="2026-11-01T09:00:00Z", release="r")

    assert ask_conversations.missing_questions() == []
