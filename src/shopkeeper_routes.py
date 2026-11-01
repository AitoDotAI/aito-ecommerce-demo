"""The Shopkeeper view's routes (ADR 0052): the Board, the routines, the stored runs.

All read-only. A shopkeeper's approvals and edited thresholds live in the browser; the server judges a
run with the thresholds a request names, so the same stored facts give a different outcome when a
threshold moves.
"""

from __future__ import annotations

import statistics

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from src import ask_conversations
from src.shopkeeper_board import board_for
from src.shopkeeper_gate import RECOMMENDED_NEVER_AUTO, GateSettings
from src.shopkeeper_run import decide_steps, load_run, release_env, snapshot_digest, stored_run_ids, tally

router = APIRouter()

ROUTINES = (
    {"id": "winback", "name": "Weekly win-back", "schedule": "Mondays 07:00 (simulated)", "built": True,
     "does": "Reads who is likely to leave, picks the next best action per customer, acts on the confident ones.",
     "kind": "rule", "why": "Aito's lift per action and a threshold decide; the same data gives the same list. No model is involved."},
    {"id": "stock", "name": "Stock-aware morning check", "schedule": "Daily 06:30", "built": False,
     "does": "Ranks reorder and overstock, proposes markdowns with their margin impact.",
     "kind": "rule", "why": "Counts of observed sales and arithmetic rank the list; a model would add nothing."},
    {"id": "portfolio", "name": "Portfolio review", "schedule": "Monthly", "built": False,
     "does": "Proposes products to retire, price changes and additions.",
     "kind": "rule", "why": "Sales, margin and the discount what-if decide; a person reads the list."},
    {"id": "product-entry", "name": "New-product entry", "schedule": "On demand", "built": False,
     "does": "Suggests the fields of a new product from similar ones.",
     "kind": "agent", "why": "The fields come from Aito's predictions; a model would write the free text and check it against them."},
    {"id": "advertising", "name": "Advertisement orchestration", "schedule": "On demand", "built": False,
     "does": "Plans which products to advertise to which segment, given stock and margin.",
     "kind": "agent", "why": "Several steps across stock, segments and copy that no single rule covers; a person approves."},
)


def settings_from(act_lift: float | None, suggest_lift: float | None, min_rows: int | None, never_auto: str | None) -> GateSettings:
    """The recommended settings, with any the request names replaced. `never_auto` is a comma list, empty for none."""
    defaults = GateSettings()
    return GateSettings(
        act_lift=defaults.act_lift if act_lift is None else act_lift,
        suggest_lift=defaults.suggest_lift if suggest_lift is None else suggest_lift,
        min_rows=defaults.min_rows if min_rows is None else min_rows,
        never_auto=defaults.never_auto if never_auto is None else frozenset(k for k in never_auto.split(",") if k))


def stale_reason(run: dict, request: Request) -> str | None:
    """Why a stored run no longer matches what the app serves, else None.

    The release must be the app's, and the numbers must be those Retention serves now: the same view through
    the same precompute store (so a sandbox or another namespace is compared with its own snapshot).
    Without that view wired in (a bare router in a test) only the release is checked.
    """
    if run["release"] != release_env():
        return f"stored for data release {run['release']}; the app serves {release_env()}"
    serve_retention = getattr(request.app.state, "ask_retention", None)
    if serve_retention is not None and snapshot_digest(serve_retention()) != run["snapshot_digest"]:
        return "Retention now serves different numbers than this run read"
    return None


def _bad_request(exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=400, content={"error": str(exc)})


@router.get("/api/shopkeeper")
def shopkeeper_overview(request: Request, act_lift: float | None = None, suggest_lift: float | None = None,
                        min_rows: int | None = None, never_auto: str | None = None):
    """The three lists of the view: the Board, the routines with their latest run, the stored runs and conversations."""
    try:
        settings = settings_from(act_lift, suggest_lift, min_rows, never_auto)
    except ValueError as exc:
        return _bad_request(exc)
    runs = [load_run(run_id) for run_id in stored_run_ids()]
    return {
        "simulated": True,
        "release": release_env(),
        "settings": _settings_view(settings, runs),
        "board": [item for run in runs for item in board_for(run, settings)],
        "routines": [{**r, "latest_run": next((run["id"] for run in runs if run["routine"] == r["id"]), None)} for r in ROUTINES],
        "runs": [{"id": run["id"], "title": run["title"], "as_of_month": run["as_of_month"],
                  "stale": stale_reason(run, request) is not None,
                  "tally": tally(decide_steps(run, settings))} for run in runs],
        "conversations": ask_conversations.list_conversations(),
    }


@router.get("/api/shopkeeper/conversations/{conversation_id}")
def shopkeeper_conversation(conversation_id: str):
    """One stored conversation with Ask the store: the question, its tool calls and results, the answer."""
    try:
        return ask_conversations.load(conversation_id)
    except ValueError as exc:
        return _bad_request(exc)
    except FileNotFoundError as exc:
        return JSONResponse(status_code=404, content={"error": str(exc)})


@router.get("/api/shopkeeper/runs/{run_id}")
def shopkeeper_run(request: Request, run_id: str, act_lift: float | None = None, suggest_lift: float | None = None,
                   min_rows: int | None = None, never_auto: str | None = None):
    """One stored run, every step judged under the thresholds the request names."""
    try:
        settings = settings_from(act_lift, suggest_lift, min_rows, never_auto)
        run = load_run(run_id)
    except ValueError as exc:
        return _bad_request(exc)
    except FileNotFoundError as exc:
        return JSONResponse(status_code=404, content={"error": str(exc)})
    decided = decide_steps(run, settings)
    return {**run, "steps": decided, "tally": tally(decided), "settings": _settings_view(settings, [run]),
            "stale": (reason := stale_reason(run, request)) is not None, "stale_reason": reason}


def _settings_view(settings: GateSettings, runs: list[dict]) -> dict:
    """The settings in force, the recommended ones beside them, and what the lifts in the stored runs look like."""
    lifts = [s["best"]["purchase_lift_p"] for run in runs for s in run["steps"] if s["best"]["action"] != "none"]
    return {
        "in_force": {"act_lift": settings.act_lift, "suggest_lift": settings.suggest_lift, "min_rows": settings.min_rows,
                     "never_auto": sorted(settings.never_auto)},
        "recommended": {"act_lift": GateSettings().act_lift, "suggest_lift": GateSettings().suggest_lift,
                        "min_rows": GateSettings().min_rows, "never_auto": sorted(RECOMMENDED_NEVER_AUTO)},
        "lifts_in_runs": ({"min": min(lifts), "median": round(statistics.median(lifts), 3), "max": max(lifts)} if lifts else None),
    }
