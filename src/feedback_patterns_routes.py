"""Prototype (no ADR yet): the stored pattern search over reviews and NPS answers, written by `scripts/feedback_patterns_prototype.py`."""

import json
from pathlib import Path

from fastapi import APIRouter

PATTERNS = Path(__file__).resolve().parent.parent / "data" / "evidence" / "feedback-patterns.json"

router = APIRouter()


@router.get("/api/feedback-patterns")
def feedback_patterns() -> dict:
    assert PATTERNS.exists(), f"{PATTERNS} is missing: run `uv run python scripts/feedback_patterns_prototype.py`"
    return json.loads(PATTERNS.read_text())
