"""Ask the store's routes (ADR 0042, amendment 2026-10-25).

Live only when the server has an Anthropic key (`ANTHROPIC_API_KEY`) **and** an admin token
(`ADMIN_TOKEN`, the sandbox's): the question is a call that costs money and goes to an outside
service, so on a public deploy it is the presenter's, not any visitor's. `GET /api/ask` says
whether the button should show; `POST /api/ask` needs the token in `X-Admin-Token`.
"""

from __future__ import annotations

import hmac
import os

import anthropic
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.aito_client import AitoError
from src.ask_store import MODEL, AskError, ask
from src.ask_tools import build_tools

router = APIRouter()

ADMIN_HEADER = "X-Admin-Token"
MAX_QUESTION_CHARS = 500


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=MAX_QUESTION_CHARS)


def _model() -> str:
    return os.environ.get("ASK_MODEL") or MODEL


def _admin_token() -> str | None:
    return os.environ.get("ADMIN_TOKEN") or None


def _configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY")) and _admin_token() is not None


@router.get("/api/ask")
def ask_status():
    """Whether Ask is on: a key and an admin token are configured."""
    return {"enabled": _configured(), "model": _model() if _configured() else None}


@router.post("/api/ask")
def ask_the_store(request: Request, body: Question):
    """Answer a question with the lever tools, read-only, over PetNord or the sandbox the request names."""
    if not _configured():
        return JSONResponse(status_code=404, content={"error": "Ask is not configured on this server"})
    given = request.headers.get(ADMIN_HEADER, "")
    if not hmac.compare_digest(given.encode(), _admin_token().encode()):
        return JSONResponse(status_code=403, content={"error": "Wrong or missing admin token"})
    state = request.app.state
    tools = build_tools(state.demo_clients.reader(request), state.ask_supply, state.ask_retention)
    try:
        return ask(body.question, tools, anthropic.Anthropic(), _model()).to_dict()
    except AskError as exc:
        return JSONResponse(status_code=422, content={"error": str(exc)})
    except AitoError as exc:
        return JSONResponse(status_code=502, content={"error": str(exc), "status_code": exc.status_code})
    except anthropic.APIError as exc:
        return JSONResponse(status_code=502, content={"error": f"The model call failed: {exc}"})
