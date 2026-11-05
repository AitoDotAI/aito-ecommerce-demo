"""The Experiments page's data (ADR 0064): each experiment's arms and whether choosing per person pays, written by `scripts/experiments_evidence.py`."""

import json
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.experiment_plan import plan

EVIDENCE = Path(__file__).resolve().parent.parent / "data" / "evidence" / "experiments.json"

router = APIRouter()


@router.get("/api/experiments")
def experiments() -> dict:
    """Stored, not computed per request: the counts and the held-out check read Aito in a few minutes (`./do experiments-evidence`)."""
    assert EVIDENCE.exists(), f"{EVIDENCE} is missing: run `./do experiments-evidence`"
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))


@router.get("/api/experiments/{experiment_id}/plan")
def experiment_plan(experiment_id: str, allocation: float = 0.5, floor: float = 0.1, guardrail: float = 10.0):
    """What a split (`allocation`, the share on the second arm), an exploration `floor` and a `guardrail` (percent) would mean for one experiment (`src/experiment_plan.py`)."""
    data = experiments()
    found = next((e for e in data["experiments"] if e["experiment_id"] == experiment_id), None)
    if found is None:
        return JSONResponse(status_code=404, content={"error": f"No experiment {experiment_id!r}"})
    try:
        return plan(found, len(data["months"]), allocation, floor, guardrail)
    except ValueError as error:
        return JSONResponse(status_code=400, content={"error": str(error)})
