"""The Customers view's routes (ADR 0053): the segments to choose from, a selection of them, and one customer's profile.

Read-only, from the stored profiles in `data/customer_profiles/` (written by `./do customer-profiles`).
A stored file for another data release is served with `stale: true`, so the page says so.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from src.customer_selection import parse, ranking_for, view
from src.customer_selection_data import actions, answers, facts, reviews
from src.demo_mode import requested_sandbox

ROOT = Path(__file__).resolve().parent.parent
PROFILES = ROOT / "data" / "customer_profiles"
RELEASE_ENV = ROOT / "data" / "release-env.json"
SEARCH_LIMIT = 12
PROFILE_FIELDS_WITHOUT_CONSENT = ("customer_id", "profiled")

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
def customer_profiles(request: Request):
    """Segment sizes, churn and spend per trait, and the response of each segment to each action.

    The profiles are the release's stored data. A request that names a sandbox (`?db=`) is answered with the same
    release data and `scope: release-not-sandbox`, so the page does not pass them off as that sandbox's."""
    scope = "release-not-sandbox" if requested_sandbox(request) else "release"
    return {**_summary(), "stale": _stale(), "scope": scope}


@lru_cache(maxsize=256)
def _selection(conditions: tuple[str, ...]) -> dict:
    return view(facts(), parse(list(conditions)), actions(), reviews(), answers(), _summary())


@router.get("/api/customer-profiles/segment")
def customer_segment(request: Request, c: list[str] = Query(default=[])):
    """Everything the view says about the customers who meet every condition `c` (repeat it: `?c=offer:mostly&c=pets:dog`);
    nothing ticked is every profiled customer. Counted from the stored facts, so any combination is answered."""
    try:
        parsed = parse(c)
    except ValueError as error:
        return JSONResponse(status_code=400, content={"error": str(error)})
    return {**_selection(tuple(f"{t}:{v}" for t, v in parsed)), "stale": _stale(),
            "scope": "release-not-sandbox" if requested_sandbox(request) else "release"}


@router.get("/api/customer-profiles/ranking")
def customer_ranking(var: str, c: list[str] = Query(default=[])):
    """The customers ranked by how much they prefer `var` (see `ranking_for`), with where the selection `c` sits in it."""
    try:
        return ranking_for(facts(), parse(c), var)
    except ValueError as error:
        return JSONResponse(status_code=400, content={"error": str(error)})


@router.get("/api/customer-profiles/customers")
def customer_search(q: str = ""):
    """Customers whose name or id contains `q`, for the lookup. Only customers who consented to profiling are found:
    a customer who did not is not searchable by name."""
    needle = q.strip().lower()
    if len(needle) < 2:
        return {"customers": []}
    hits = [t for t in _customers().values() if t["profiled"] and (needle in t["name"].lower() or needle in t["customer_id"].lower())]
    return {"customers": [{"customer_id": t["customer_id"], "name": t["name"], "profiled": True} for t in hits[:SEARCH_LIMIT]]}


@router.get("/api/customer-profiles/customers/{customer_id}")
def customer_profile(customer_id: str):
    """One customer's traits. A customer who did not consent to behavioural profiling has none: not even their name."""
    traits = _customers().get(customer_id)
    if traits is None:
        return JSONResponse(status_code=404, content={"error": f"No customer {customer_id!r} in the stored profiles"})
    if not traits["profiled"]:
        return {**{k: traits[k] for k in PROFILE_FIELDS_WITHOUT_CONSENT}, "stale": _stale()}
    return {**traits, "stale": _stale()}
