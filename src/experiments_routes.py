"""The Experiments page's data (ADR 0064): each experiment's arms and whether choosing per person pays, written by `scripts/experiments_evidence.py`."""

import json
from pathlib import Path

from fastapi import APIRouter

EVIDENCE = Path(__file__).resolve().parent.parent / "data" / "evidence" / "experiments.json"

router = APIRouter()


@router.get("/api/experiments")
def experiments() -> dict:
    """Stored, not computed per request: the counts and the held-out check read Aito in a few minutes (`./do experiments-evidence`)."""
    assert EVIDENCE.exists(), f"{EVIDENCE} is missing: run `./do experiments-evidence`"
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))
