"""The Customers view's routes (ADR 0053): segments, who responds to what, and one customer's profile.

Read-only, from the stored profiles in `data/customer_profiles/` (written by `./do customer-profiles`).
A stored file for another data release is served with `stale: true`, so the page says so.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

ROOT = Path(__file__).resolve().parent.parent
PROFILES = ROOT / "data" / "customer_profiles"
RELEASE_ENV = ROOT / "data" / "release-env.json"
SEARCH_LIMIT = 12

router = APIRouter()


@lru_cache(maxsize=1)
def _summary() -> dict:
    return json.loads((PROFILES / "summary.json").read_text())


@lru_cache(maxsize=1)
def _customers() -> dict[str, dict]:
    return {t["customer_id"]: t for t in json.loads((PROFILES / "customers.json").read_text())}


def _stale() -> bool:
    return _summary()["release"] != json.loads(RELEASE_ENV.read_text())["env"]


@router.get("/api/customer-profiles")
def customer_profiles():
    """Segment sizes, churn and spend per trait, and the response of each segment to each action."""
    return {**_summary(), "stale": _stale()}


@router.get("/api/customer-profiles/customers")
def customer_search(q: str = ""):
    """Customers whose name or id contains `q` (profiled or not), for the lookup."""
    needle = q.strip().lower()
    if len(needle) < 2:
        return {"customers": []}
    hits = [t for t in _customers().values() if needle in t["name"].lower() or needle in t["customer_id"].lower()]
    return {"customers": [{"customer_id": t["customer_id"], "name": t["name"], "profiled": t["profiled"]} for t in hits[:SEARCH_LIMIT]]}


@router.get("/api/customer-profiles/customers/{customer_id}")
def customer_profile(customer_id: str):
    """One customer's traits. A customer who did not consent to behavioural profiling has none to show."""
    traits = _customers().get(customer_id)
    if traits is None:
        return JSONResponse(status_code=404, content={"error": f"No customer {customer_id!r} in the stored profiles"})
    return {**traits, "stale": _stale()}
