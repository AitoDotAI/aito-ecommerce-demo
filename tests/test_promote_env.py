"""./do env-promote (ADR 0035): the release env goes onto master, after a backup, and only when it is the release."""

import httpx
import pytest

from scripts.promote_env import BackupExists, NotTheRelease, promote
from src.release_file import Release

BASE = "https://shared.example/db/demo/api/v1"
RELEASE = Release("release4", {"orders": 10, "customers": 3})


def client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), headers={"x-api-key": "k"})


class Server:
    """A fake Aito that remembers what it was asked to write."""

    def __init__(self, envs=("master", "release4")):
        self.envs = set(envs)
        self.writes: list[tuple[str, str, dict | None]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/db/demo/api/v1")
        if request.method == "GET" and path == "/_envs":
            return httpx.Response(200, json={"envs": [{"name": n} for n in sorted(self.envs)]})
        body = None if not request.content else __import__("json").loads(request.content)
        self.writes.append((request.method, path, body))
        return httpx.Response(200, json={})


def counts_ok(_env):
    return {"orders": 10, "customers": 3}


def test_a_dry_run_says_what_it_would_do_and_writes_nothing():
    server = Server()

    plan = promote(client(server), BASE, "release4", RELEASE, counts_ok, apply=False, backup_name="master-backup-test")

    assert server.writes == []
    assert "master-backup-test" in plan and "release4" in plan


def test_applying_takes_the_backup_first_and_then_promotes_the_env():
    server = Server()

    promote(client(server), BASE, "release4", RELEASE, counts_ok, apply=True, backup_name="master-backup-test")

    assert server.writes == [("POST", "/_envs", {"name": "master-backup-test", "basedOn": "env.master"}), ("POST", "/_envs/release4/promote", None)]


def test_master_can_never_be_promoted_onto_itself():
    with pytest.raises(ValueError, match="master"):
        promote(client(Server()), BASE, "master", RELEASE, counts_ok, apply=True, backup_name="b")


def test_an_env_that_is_not_the_release_is_refused_before_anything_is_written():
    server = Server()

    with pytest.raises(NotTheRelease, match="orders"):
        promote(client(server), BASE, "release4", RELEASE, lambda _env: {"orders": 9, "customers": 3}, apply=True, backup_name="b")

    assert server.writes == []


def test_an_env_that_does_not_exist_is_refused():
    with pytest.raises(ValueError, match="no env"):
        promote(client(Server(envs=("master",))), BASE, "release4", RELEASE, counts_ok, apply=True, backup_name="b")


def test_a_backup_name_already_taken_is_refused_and_nothing_is_promoted():
    server = Server(envs=("master", "release4", "master-backup-test"))

    with pytest.raises(BackupExists):
        promote(client(server), BASE, "release4", RELEASE, counts_ok, apply=True, backup_name="master-backup-test")

    assert server.writes == []


def test_if_the_backup_fails_the_env_is_not_promoted():
    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json={"envs": [{"name": "master"}, {"name": "release4"}]})
        return httpx.Response(500, text="no space")

    with pytest.raises(RuntimeError, match="backup"):
        promote(client(handler), BASE, "release4", RELEASE, counts_ok, apply=True, backup_name="b")
