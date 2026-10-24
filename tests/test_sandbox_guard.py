"""No write reaches a master (ADR 0043).

While sandboxes are configured, three clients exist:

- PetNord's database: `writes="none"`, every write raises before any HTTP;
- the sandbox database's master (the template): `writes="envs"`, it may
  create and delete branches and write no data;
- one client per `tmp-` branch: the only one that writes data.

A request reads PetNord's database unless it names a live branch, and a
name that isn't one is a 400, never PetNord's data.
"""

import pytest
from pytest_httpx import HTTPXMock
from starlette.requests import Request

from src.aito_client import WRITES_ENVS, WRITES_NONE, AitoClient, ReadOnlyClientError
from src.config import Config
from src.demo_mode import DemoClients
from src.product_levers import add_review, set_offer
from src.sandbox_config import load_sandbox_setting
from src.sandbox_envs import SandboxBranches, SandboxEnvError
from tests.fake_sandbox_aito import BRANCH, SANDBOX_URL

PETNORD_URL = "https://shared.aito.ai/db/aito-ecommerce-demo"
PETNORD = Config(aito_api_url=PETNORD_URL, aito_api_key="ro", public_demo=False, use_v2=True, aito_env="master")
TEMPLATE = Config(aito_api_url=SANDBOX_URL, aito_api_key="rw", public_demo=False, use_v2=True, aito_env="master")


def request(query: str = "", headers: dict | None = None) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request({"type": "http", "method": "GET", "path": "/api/shop/grid", "query_string": query.encode(),
                    "headers": raw})


def envs(httpx_mock: HTTPXMock, *names: str) -> None:
    httpx_mock.add_response(url=f"{SANDBOX_URL}/api/v2/_envs", method="GET", is_reusable=True,
                            json={"envs": [{"name": "master", "isMaster": True},
                                           *({"name": n, "isMaster": False} for n in names)]})


@pytest.fixture
def clients() -> DemoClients:
    return DemoClients(petnord=AitoClient(PETNORD, writes=WRITES_NONE),
                       branches=SandboxBranches(AitoClient(TEMPLATE, writes=WRITES_ENVS)))


# ── The clients' fences ─────────────────────────────────────────────


@pytest.mark.parametrize("method, path", [("POST", "/data/product_states"), ("POST", "/data/_delete"),
                                          ("PUT", "/schema/reviews"), ("DELETE", "/schema/reviews"),
                                          ("POST", "/_envs")])
def test_petnords_client_refuses_every_write_before_sending_it(method, path, httpx_mock):
    client = AitoClient(PETNORD, writes=WRITES_NONE)

    with pytest.raises(ReadOnlyClientError):
        client._request(method, path, json={})

    assert httpx_mock.get_requests() == []


def test_petnords_client_still_reads(httpx_mock):
    httpx_mock.add_response(url=f"{PETNORD_URL}/api/v2/_search", json={"total": 0, "hits": []})

    assert AitoClient(PETNORD, writes=WRITES_NONE).search("products", limit=0)["total"] == 0


@pytest.mark.parametrize("method, path", [("POST", "/data/product_states"), ("POST", "/data/reviews/batch"),
                                          ("PUT", "/schema/products"), ("DELETE", "/schema/products")])
def test_the_templates_client_writes_no_data(method, path, httpx_mock):
    with pytest.raises(ReadOnlyClientError):
        AitoClient(TEMPLATE, writes=WRITES_ENVS)._request(method, path, json={})
    assert httpx_mock.get_requests() == []


def test_a_lever_through_petnords_client_raises_and_sends_no_write(httpx_mock):
    httpx_mock.add_response(url=f"{PETNORD_URL}/api/v2/_search", is_reusable=True, json={"total": 1, "hits": [
        {"product_sku": "SKU-PT-0563", "month": "2026-04", "list_price_eur": 20.0, "rating_band": "4",
         "discount_band": "none", "age": "established", "rival_launched": False, "price_change": "none",
         "review_id": "REV-1", "rating": 4}]})
    client = AitoClient(PETNORD, writes=WRITES_NONE)

    with pytest.raises(ReadOnlyClientError):
        set_offer(client, "SKU-PT-0563", "20+")
    with pytest.raises(ReadOnlyClientError):
        add_review(client, "SKU-PT-0563", 5, "Lovely")

    assert {r.url.path.rsplit("/", 1)[-1] for r in httpx_mock.get_requests()} == {"_search"}


def test_with_sandboxes_petnords_client_must_be_read_only():
    with pytest.raises(ValueError, match="read-only"):
        DemoClients(petnord=AitoClient(PETNORD), branches=SandboxBranches(AitoClient(TEMPLATE, writes=WRITES_ENVS)))


# ── The settings ────────────────────────────────────────────────────


@pytest.mark.parametrize("url, on", [
    ("https://shared.aito.ai/db/aito-ecommerce-sandbox", True),
    ("https://shared.aito.ai/db/aito-ecommerce-demo", False),       # PetNord's: no "sandbox"
    ("https://shared.aito.ai/db/aito-ecommerce-demo/env/sandbox", False),   # an env, not a database
    ("http://localhost:8080", False),
])
def test_sandbox_mode_needs_a_database_named_sandbox(url, on, monkeypatch):
    monkeypatch.setenv("AITO_SANDBOX_URL", url)
    monkeypatch.setenv("AITO_SANDBOX_API_KEY", "rw")

    assert (load_sandbox_setting(PETNORD).config is not None) is on


def test_sandbox_mode_is_off_without_both_settings(monkeypatch):
    monkeypatch.setenv("AITO_SANDBOX_URL", SANDBOX_URL)
    monkeypatch.delenv("AITO_SANDBOX_API_KEY", raising=False)

    setting = load_sandbox_setting(PETNORD)

    assert setting.config is None and "not both set" in setting.off_reason


# ── Routing a request, failing closed ───────────────────────────────


def test_a_request_naming_no_sandbox_reads_petnord(clients):
    assert clients.reader(request()) is clients.petnord


def test_a_live_branch_named_in_the_url_or_the_header_is_read_and_written_there(clients, httpx_mock):
    envs(httpx_mock, BRANCH)

    for named in (request(f"db={BRANCH}"), request(headers={"X-Aito-Env": BRANCH})):
        client = clients.reader(named)
        assert client.env == BRANCH and client.writes == "any"
        assert client._url("/data/reviews") == f"{SANDBOX_URL}/env/{BRANCH}/api/v2/data/reviews"


@pytest.mark.parametrize("name", [
    "master", "env.master", "observable", "tmp-fixed", "tmp-2026-10-26-15-30-00-3F9C2A1B7D4E6F80",
    "tmp-2026-10-26-15-30-00-3f9c2a1b7d4e6f8", f"{BRANCH}/../../api", f" {BRANCH}",
])
def test_any_other_name_is_refused_never_read_as_petnord(clients, httpx_mock, name):
    with pytest.raises(SandboxEnvError):
        clients.reader(request(headers={"X-Aito-Env": name}))

    # Refused on its form alone: not even the env list is asked.
    assert httpx_mock.get_requests() == []


def test_an_expired_branch_is_refused(clients, httpx_mock):
    envs(httpx_mock)    # the branch was reaped

    with pytest.raises(SandboxEnvError, match="expired"):
        clients.reader(request(f"db={BRANCH}"))


def test_a_request_naming_two_different_sandboxes_is_refused(clients):
    with pytest.raises(SandboxEnvError, match="two sandboxes"):
        clients.reader(request(f"db={BRANCH}", {"X-Aito-Env": BRANCH.replace("3f9c", "0000")}))


def test_a_server_without_sandboxes_refuses_a_sandbox_name():
    clients = DemoClients(petnord=AitoClient(PETNORD), branches=None)

    with pytest.raises(SandboxEnvError, match="no sandboxes"):
        clients.reader(request(f"db={BRANCH}"))


def test_a_lever_needs_a_named_sandbox(clients):
    with pytest.raises(SandboxEnvError, match="needs a sandbox"):
        clients.sandbox(request())
