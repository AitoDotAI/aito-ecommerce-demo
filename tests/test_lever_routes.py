"""The sandbox's HTTP routes (ADR 0043): 404 without a sandbox, the admin
token on "New sandbox", 429 when five are live, 400 for a bad name.

The routes are mounted on a bare app here, with the same `app.state` the
real app sets up, so no test reaches a real Aito.
"""

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from src.aito_client import WRITES_ENVS, WRITES_NONE, AitoClient
from src.config import Config
from src.demo_mode import DemoClients
from src.lever_routes import router
from src.sandbox_envs import SandboxBranches, SandboxEnvError, SandboxFullError
from tests.fake_sandbox_aito import BRANCH, SANDBOX_URL

PETNORD = Config(aito_api_url="https://shared.aito.ai/db/aito-ecommerce-demo", aito_api_key="ro",
                 public_demo=False, use_v2=True, aito_env="master")
TEMPLATE = Config(aito_api_url=SANDBOX_URL, aito_api_key="rw", public_demo=False, use_v2=True, aito_env="master")
TOKEN = "s3cret-admin-token"


class StubBranches(SandboxBranches):
    """Branches without HTTP: `create` answers a fixed name, or is full."""

    def __init__(self, *, full: bool = False) -> None:
        super().__init__(AitoClient(TEMPLATE, writes=WRITES_ENVS))
        self.full = full
        self.created = 0
        self.deleted: list[str] = []

    def delete(self, name: str) -> None:
        self.deleted.append(name)

    def create(self) -> str:
        if self.full:
            raise SandboxFullError("5 sandboxes are live, the most there can be")
        self.created += 1
        return BRANCH

    def names(self, *, fresh: bool = False) -> set[str]:
        return {"master", BRANCH}


class StubGate:
    def status(self) -> dict:
        return {"state": "ready"}


def app(*, sandbox: bool = True, token: str | None = TOKEN, full: bool = False) -> TestClient:
    api = FastAPI()
    api.include_router(router)
    branches = StubBranches(full=full) if sandbox else None
    api.state.demo_clients = DemoClients(petnord=AitoClient(PETNORD, writes=WRITES_NONE if sandbox else "any"),
                                         branches=branches)
    api.state.sandbox_gate = StubGate()
    api.state.admin_token = token

    @api.exception_handler(SandboxEnvError)
    async def bad_name(request, exc):
        return JSONResponse(status_code=400, content={"error": str(exc)})
    return TestClient(api)


@pytest.fixture(autouse=True)
def no_warm_up(monkeypatch):
    monkeypatch.setattr("src.lever_routes.warm_up", lambda client: [])


@pytest.mark.parametrize("method, path, body", [
    ("POST", "/api/levers/offer", {"sku": "SKU-PT-0563", "band": "20+"}),
    ("POST", "/api/levers/review", {"sku": "SKU-PT-0563", "stars": 1, "text": "Small"}),
    ("GET", "/api/levers/state?sku=SKU-PT-0563", None),
    ("POST", "/api/sandbox", None),
])
def test_without_a_sandbox_every_lever_route_is_404(method, path, body):
    client = app(sandbox=False)

    response = client.request(method, path, json=body, headers={"X-Admin-Token": TOKEN})

    assert response.status_code == 404


def test_without_a_sandbox_the_status_says_so_and_the_header_shows_no_toggle():
    assert app(sandbox=False).get("/api/sandbox").json() == {"configured": False}


def test_new_sandbox_without_a_configured_admin_token_is_404():
    assert app(token=None).post("/api/sandbox", headers={"X-Admin-Token": "anything"}).status_code == 404


@pytest.mark.parametrize("given", ["", "wrong", TOKEN + "x"])
def test_new_sandbox_with_a_wrong_token_is_403(given):
    assert app().post("/api/sandbox", headers={"X-Admin-Token": given}).status_code == 403


def test_new_sandbox_returns_the_branch_its_expiry_and_where_it_starts_from():
    body = app().post("/api/sandbox", headers={"X-Admin-Token": TOKEN}).json()

    assert body == {"env": BRANCH, "expires_at": "2026-10-26T18:30:00+00:00",
                    "starts_from": "the release data (the template)", "replaced": None}


def test_new_sandbox_from_inside_one_deletes_the_one_it_replaces():
    client = app()
    branches = client.app.state.demo_clients.branches

    body = client.post("/api/sandbox", headers={"X-Admin-Token": TOKEN, "X-Aito-Env": BRANCH}).json()

    assert body["replaced"] == BRANCH and branches.deleted == [BRANCH]


def test_new_sandbox_when_five_are_live_is_429_with_the_reason():
    response = app(full=True).post("/api/sandbox", headers={"X-Admin-Token": TOKEN})

    assert response.status_code == 429 and "5 sandboxes are live" in response.json()["error"]


def test_a_lever_without_a_named_sandbox_is_400():
    response = app().post("/api/levers/offer", json={"sku": "SKU-PT-0563", "band": "20+"})

    assert response.status_code == 400 and "needs a sandbox" in response.json()["error"]


def test_the_status_of_a_named_sandbox_gives_its_expiry():
    body = app().get(f"/api/sandbox?db={BRANCH}").json()

    assert body["configured"] and body["can_create"] and body["sandbox"]["env"] == BRANCH


def test_the_status_of_a_malformed_name_is_400():
    assert app().get("/api/sandbox?db=master").status_code == 400
