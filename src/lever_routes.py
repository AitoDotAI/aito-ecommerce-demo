"""The sandbox's routes (ADR 0043): sandboxes, and the owner's two levers.

Every route here answers 404 unless a sandbox database is configured
(`src/sandbox_config.py`). A lever writes only to the `tmp-` branch the
request names (`?db=` or `X-Aito-Env`); PetNord's client is read-only
then, and the sandbox database's master manages branches only, so no
route here can write to either master.

"New sandbox" (`POST /api/sandbox`) needs the admin token in
`X-Admin-Token`; without ADMIN_TOKEN configured it is 404 too.
"""

from __future__ import annotations

import hmac
import threading

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.aito_client import AitoError
from src.lookup_errors import UnknownProductError
from src.product_levers import LeverInputError, add_review, read_states, set_offer
from src.demo_mode import requested_sandbox
from src.sandbox_envs import MAX_AGE, MAX_LIVE, SandboxEnvError, SandboxFullError, expires_at, is_branch_name
from src.sandbox_warmup import warm_up
from src.shop_history import NEXT_MONTH

router = APIRouter()

ADMIN_HEADER = "X-Admin-Token"
NOT_CONFIGURED = {"error": "No sandbox is configured on this server"}


class OfferLever(BaseModel):
    sku: str
    band: str           # "none" | "10-15" | "15-20" | "20+"


class ReviewLever(BaseModel):
    sku: str
    stars: int
    text: str


@router.get("/api/sandbox")
def sandbox_status(request: Request):
    """Whether this server has sandboxes, and, for a request that names one,
    when it expires. The header shows "New sandbox" only when `can_create`."""
    state = request.app.state
    if state.demo_clients.branches is None:
        return {"configured": False}
    status = {
        "configured": True,
        "can_create": state.admin_token is not None,
        "month": NEXT_MONTH,
        "max_live": MAX_LIVE,
        "max_age_hours": MAX_AGE.total_seconds() / 3600,
        "template": state.sandbox_gate.status(),
        "sandbox": None,
    }
    client = state.demo_clients.reader(request)       # 400 for a name that isn't a live branch
    if client is not state.demo_clients.petnord:
        status["sandbox"] = _described(client.env)
    return status


@router.post("/api/sandbox")
def new_sandbox(request: Request):
    """A new branch of the template: its name goes in the page's `?db=`."""
    state = request.app.state
    if state.demo_clients.branches is None or state.admin_token is None:
        return JSONResponse(status_code=404, content=NOT_CONFIGURED)
    given = request.headers.get(ADMIN_HEADER, "")
    if not hmac.compare_digest(given.encode(), state.admin_token.encode()):
        return JSONResponse(status_code=403, content={"error": "Wrong or missing admin token"})
    branches = state.demo_clients.branches
    # "New sandbox" from inside one is the reset: the old branch is deleted
    # at once, since Aito keeps a capped number of envs in memory.
    replaced = requested_sandbox(request)
    if replaced is not None and not is_branch_name(replaced):
        raise SandboxEnvError(f"{replaced!r} is not a sandbox name, so it can't be replaced")
    try:
        if replaced is not None and replaced in branches.names(fresh=True):
            branches.delete(replaced)
        name = branches.create()
    except SandboxFullError as exc:
        return JSONResponse(status_code=429, content={"error": str(exc)})
    except AitoError as exc:
        return JSONResponse(status_code=502, content={"error": str(exc), "status_code": exc.status_code})
    # The branch's first queries are the slow ones; take them before the room does.
    branch = branches.client(name)
    threading.Thread(target=warm_up, args=(branch,), name=f"warm-{name}", daemon=True).start()
    return {**_described(name), "replaced": replaced}


@router.get("/api/levers/state")
def lever_state(request: Request, sku: str):
    """The product's April state and, once a lever was pulled, its 2026-05 state."""
    return _lever(request, lambda client: read_states(client, sku))


@router.post("/api/levers/offer")
def offer_lever(request: Request, lever: OfferLever):
    """Put the product on offer (or end it) in 2026-05; returns the row read back."""
    return _lever(request, lambda client: set_offer(client, lever.sku, lever.band).to_dict())


@router.post("/api/levers/review")
def review_lever(request: Request, lever: ReviewLever):
    """Add a review dated 2026-05 and recompute its stars; says whether the band changed."""
    return _lever(request, lambda client: add_review(client, lever.sku, lever.stars, lever.text).to_dict())


def _lever(request: Request, run):
    clients = request.app.state.demo_clients
    if clients.branches is None:
        return JSONResponse(status_code=404, content=NOT_CONFIGURED)
    branch = clients.sandbox(request)       # 400 unless the request names a live branch
    try:
        return run(branch)
    except UnknownProductError as exc:
        return JSONResponse(status_code=404, content={"error": str(exc)})
    except LeverInputError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except AitoError as exc:
        return JSONResponse(status_code=502, content={"error": str(exc), "status_code": exc.status_code})


def _described(name: str) -> dict:
    return {"env": name, "expires_at": expires_at(name).isoformat(), "starts_from": "the release data (the template)"}
