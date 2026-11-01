"""Stored Ask conversations (ADR 0054): a question, what the model called, its answer.

Kept as one JSON file each in `data/ask_conversations/`, recorded from a server where Ask is on
(`./do record-conversation`), so a visitor can read and replay a conversation without a key. Nothing
here calls a model. A stored file is checked when read: a missing field fails loudly.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

DIRECTORY = Path(__file__).resolve().parent.parent / "data" / "ask_conversations"

# The conversations a demo should have stored: `./do record-conversations` records the ones that are missing.
PREDEFINED_QUESTIONS = (
    "What should I reorder this week, and what is overstocked?",
    "Which customers are most likely to leave, and what should I do for them?",
    "Which product is the best candidate for an offer next month, and what would it earn?",
)

ID_PATTERN =re.compile(r"[a-z0-9][a-z0-9-]{0,79}")
REQUIRED = ("id", "asked_at", "release", "question", "answer", "model", "input_tokens", "output_tokens", "tool_calls")


def _check_id(conversation_id: str) -> str:
    if not ID_PATTERN.fullmatch(conversation_id):
        raise ValueError(f"Not a conversation id: {conversation_id!r}")
    return conversation_id


def _slug(question: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", question.lower()).strip("-")[:40].strip("-") or "question"


def save(question: str, answer: dict, asked_at: str, release: str) -> str:
    """Store an answer (an `Answer.to_dict()`) as a conversation; returns its id."""
    conversation_id = f"{re.sub(r'[^0-9]', '', asked_at)[:14]}-{_slug(question)}"
    record = {"id": _check_id(conversation_id), "asked_at": asked_at, "release": release, "question": question, **answer}
    missing = [k for k in REQUIRED if k not in record]
    assert not missing, f"conversation {conversation_id} lacks {missing}"
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    (DIRECTORY / f"{conversation_id}.json").write_text(json.dumps(record, indent=2, default=str) + "\n")
    return conversation_id


def load(conversation_id: str) -> dict:
    path = DIRECTORY / f"{_check_id(conversation_id)}.json"
    if not path.exists():
        raise FileNotFoundError(f"No stored conversation {conversation_id}")
    record = json.loads(path.read_text())
    missing = [k for k in REQUIRED if k not in record]
    if missing:
        raise ValueError(f"Stored conversation {conversation_id} lacks {missing}")
    return record


def list_conversations() -> list[dict]:
    """The stored conversations, newest first: what the list on the Shopkeeper view needs, not the tool results."""
    if not DIRECTORY.exists():
        return []
    records = [load(path.stem) for path in sorted(DIRECTORY.glob("*.json"))]
    records.sort(key=lambda r: r["asked_at"], reverse=True)
    return [{"id": r["id"], "asked_at": r["asked_at"], "question": r["question"], "model": r["model"],
             "tool_calls": len(r["tool_calls"]), "tokens": r["input_tokens"] + r["output_tokens"], "release": r["release"]}
            for r in records]


def missing_questions() -> list[str]:
    """The predefined questions with no stored conversation yet (matched on the exact question)."""
    stored = {c["question"] for c in list_conversations()}
    return [q for q in PREDEFINED_QUESTIONS if q not in stored]
