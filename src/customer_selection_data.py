"""The stored files the Customers view counts a selection from (written by `./do customer-profiles`, read once)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
PROFILES = DATA / "customer_profiles"


def _read(path: Path):
    return json.loads(path.read_text())


@lru_cache(maxsize=1)
def summary() -> dict:
    return _read(PROFILES / "summary.json")


@lru_cache(maxsize=1)
def facts() -> dict:
    return _read(PROFILES / "facts.json")


@lru_cache(maxsize=1)
def actions() -> list[dict]:
    return _read(DATA / "customer_actions.json")


@lru_cache(maxsize=1)
def reviews() -> list[dict]:
    return _read(DATA / "reviews.json")


@lru_cache(maxsize=1)
def answers() -> list[dict]:
    return _read(DATA / "nps_responses.json")
