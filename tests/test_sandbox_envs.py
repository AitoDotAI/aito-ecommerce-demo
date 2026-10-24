"""Sandbox branches (ADR 0043): named, created, capped and reaped.

The env API of the sandbox database (Aito v2):

    GET    /db/<db>/api/v2/_envs          → {"envs": [{"name": "…", "isMaster": …}, …]}
    POST   /db/<db>/api/v2/_envs          {"name": "tmp-…", "basedOn": "env.master"}
    DELETE /db/<db>/api/v2/_envs/<name>

A branch is named `tmp-<UTC time>-<16 hex>` and lives three hours.
"""

import json
import logging
import threading
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from pytest_httpx import HTTPXMock

from src.aito_client import WRITES_ENVS, AitoClient
from src.config import Config
from src.sandbox_envs import (MAX_LIVE, SandboxBranches, SandboxFullError, created_at, is_branch_name,
                              new_branch_name)
from tests.fake_sandbox_aito import SANDBOX_URL

ENVS = f"{SANDBOX_URL}/api/v2/_envs"
NOW = datetime(2026, 10, 26, 15, 30, tzinfo=timezone.utc)
TEMPLATE = Config(aito_api_url=SANDBOX_URL, aito_api_key="rw", public_demo=False, use_v2=True, aito_env="master")


def branch_at(hours_ago: float, suffix: str = "0123456789abcdef") -> str:
    return f"tmp-{NOW - timedelta(hours=hours_ago):%Y-%m-%d-%H-%M-%S}-{suffix}"


class FakeEnvs:
    """The sandbox database's env list, created into and deleted from."""

    def __init__(self, *names: str) -> None:
        self.names = ["master", *names]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"envs": [{"name": n, "isMaster": n == "master"} for n in self.names]})
        if request.method == "POST":
            body = json.loads(request.read())
            assert body["basedOn"] == "env.master"
            self.names.append(body["name"])
            return httpx.Response(200, json={"name": body["name"]})
        self.names.remove(request.url.path.rsplit("/", 1)[-1])
        return httpx.Response(200, json={})


@pytest.fixture
def branches() -> SandboxBranches:
    return SandboxBranches(AitoClient(TEMPLATE, writes=WRITES_ENVS), clock=lambda: NOW)


def serve(httpx_mock: HTTPXMock, envs: FakeEnvs) -> FakeEnvs:
    httpx_mock.add_callback(envs, is_reusable=True)
    return envs


def test_a_new_name_holds_the_utc_time_and_64_random_bits():
    name = new_branch_name(NOW)

    assert name.startswith("tmp-2026-10-26-15-30-00-") and len(name.rsplit("-", 1)[1]) == 16
    assert is_branch_name(name) and created_at(name) == NOW
    assert new_branch_name(NOW) != name


def test_new_sandbox_branches_the_template_and_checks_it_exists(branches, httpx_mock):
    envs = serve(httpx_mock, FakeEnvs())

    name = branches.create()

    assert name in envs.names and is_branch_name(name)
    post = next(r for r in httpx_mock.get_requests() if r.method == "POST")
    assert str(post.url) == ENVS and json.loads(post.read()) == {"name": name, "basedOn": "env.master"}


def test_at_five_live_sandboxes_new_sandbox_is_refused(branches, httpx_mock):
    serve(httpx_mock, FakeEnvs(*(branch_at(h / 2, f"{h:016x}") for h in range(MAX_LIVE))))

    with pytest.raises(SandboxFullError, match="5 sandboxes are live"):
        branches.create()
    assert not any(r.method == "POST" for r in httpx_mock.get_requests())


def test_new_sandbox_reaps_the_expired_first_so_they_dont_count(branches, httpx_mock):
    envs = serve(httpx_mock, FakeEnvs(*(branch_at(4 + h, f"{h:016x}") for h in range(MAX_LIVE))))

    name = branches.create()

    assert envs.names == ["master", name]


def test_the_reaper_deletes_branches_older_than_three_hours_only(branches, httpx_mock):
    old, young = branch_at(3.1), branch_at(2.9, "fedcba9876543210")
    envs = serve(httpx_mock, FakeEnvs(old, young, "observable"))

    assert branches.reap() == [old]
    assert envs.names == ["master", young, "observable"]
    deletes = [str(r.url) for r in httpx_mock.get_requests() if r.method == "DELETE"]
    assert deletes == [f"{ENVS}/{old}"]


def test_the_reaper_never_deletes_a_malformed_tmp_name_but_logs_it(branches, httpx_mock, caplog):
    malformed = "tmp-2020-01-01-00-00-00-fixed"
    envs = serve(httpx_mock, FakeEnvs(malformed))

    with caplog.at_level(logging.ERROR):
        assert branches.reap() == []

    assert malformed in envs.names and malformed in caplog.text


def test_a_reaped_branch_can_no_longer_be_used(branches, httpx_mock):
    old = branch_at(4)
    serve(httpx_mock, FakeEnvs(old))
    branches.client(old)

    branches.reap()

    with pytest.raises(ValueError, match="expired"):
        branches.client(old)


def test_only_a_branch_name_can_be_deleted(branches, httpx_mock):
    with pytest.raises(ValueError, match="not a sandbox branch"):
        branches.delete("master")
    assert httpx_mock.get_requests() == []


def test_a_branch_is_re_warmed_on_first_use_and_after_25_minutes_idle(httpx_mock):
    young = branch_at(1)
    serve(httpx_mock, FakeEnvs(young))
    warmed, seconds = [], [1000.0]
    done = threading.Semaphore(0)

    def on_resume(client):
        warmed.append(client.env)
        done.release()
    branches = SandboxBranches(AitoClient(TEMPLATE, writes=WRITES_ENVS), clock=lambda: NOW,
                               on_resume=on_resume, monotonic=lambda: seconds[0])

    for idle in (0, 60, 26 * 60):
        seconds[0] += idle
        branches.client(young)

    assert done.acquire(timeout=2) and done.acquire(timeout=2)
    # The first use and the use after 26 minutes idle; not the one after 1 minute.
    assert warmed == [young, young]
