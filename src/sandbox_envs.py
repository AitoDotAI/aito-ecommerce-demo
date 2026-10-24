"""Throwaway sandbox branches of the sandbox database (ADR 0043, amendment 2).

Aito v2 branches an env copy-on-write in milliseconds, without a load:

    POST   /db/<db>/api/v2/_envs          {"name": "<name>", "basedOn": "env.master"}
    DELETE /db/<db>/api/v2/_envs/<name>
    GET    /db/<db>/api/v2/_envs          → {"envs": [{"name": "…", "isMaster": false}, …]}

and an env is addressed only by its URL path, `/db/<db>/env/<name>/api/v2/…`.
Keys are per database, so the sandbox is a database of its own; its
master is the template, loaded once from the release fixtures
(`./do sandbox-template-load`). Each "New sandbox" is a branch of it:

    tmp-2026-10-26-15-30-00-3f9c2a1b7d4e6f80

created (UTC) at the time in its name, with 64 random bits so a link can't
be guessed. Only names of exactly that form are ever read, written or
deleted. A branch lives MAX_AGE; the reaper deletes older ones, and at
most MAX_LIVE exist at a time.
"""

from __future__ import annotations

import logging
import re
import secrets
import threading
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from src.aito_client import WRITES_ANY, WRITES_ENVS, AitoClient, AitoError

logger = logging.getLogger(__name__)

BRANCH_PATTERN = re.compile(r"^tmp-\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}-[0-9a-f]{16}$")
TEMPLATE = "env.master"
MAX_AGE = timedelta(hours=3)
MAX_LIVE = 5
LIST_TTL_SECONDS = 30.0     # how long a read of the env list is trusted
# Aito evicts an env idle for 30 minutes from memory (it isn't deleted); its
# next query re-links it cold. A branch idle longer than this is re-warmed.
RESUME_AFTER_SECONDS = 25 * 60


class SandboxEnvError(ValueError):
    """A request named a sandbox that isn't a live `tmp-` branch: answered 400."""


class SandboxFullError(RuntimeError):
    """MAX_LIVE branches exist already: "New sandbox" answers 429."""


def new_branch_name(now: datetime) -> str:
    return f"tmp-{now.astimezone(timezone.utc):%Y-%m-%d-%H-%M-%S}-{secrets.token_hex(8)}"


def is_branch_name(name: str) -> bool:
    return bool(BRANCH_PATTERN.fullmatch(name))


def created_at(name: str) -> datetime:
    """The UTC time in a branch's name. Raises SandboxEnvError for any other name."""
    if not is_branch_name(name):
        raise SandboxEnvError(f"{name!r} is not a sandbox branch name")
    return datetime.strptime(name[4:23], "%Y-%m-%d-%H-%M-%S").replace(tzinfo=timezone.utc)


def expires_at(name: str) -> datetime:
    return created_at(name) + MAX_AGE


class SandboxBranches:
    """The sandbox database's branches: list, create, delete, and a client per branch.

    `admin` is the sandbox database's master client, allowed to create and
    delete branches only (`WRITES_ENVS`): it never writes data.
    """

    def __init__(self, admin: AitoClient, *, clock=lambda: datetime.now(timezone.utc),
                 on_resume=None, monotonic=time.monotonic) -> None:
        """`on_resume(client)` runs, on a thread, when a branch is used for the
        first time in this process or after RESUME_AFTER_SECONDS idle."""
        if admin.writes != WRITES_ENVS:
            raise ValueError("The sandbox database's master client must manage branches only (writes='envs')")
        self._admin = admin
        self._clock = clock
        self._lock = threading.Lock()
        self._listed: tuple[float, set[str]] | None = None
        self._clients: dict[str, AitoClient] = {}
        self._last_used: dict[str, float] = {}
        self._on_resume = on_resume
        self._monotonic = monotonic

    def names(self, *, fresh: bool = False) -> set[str]:
        """Every env name in the sandbox database, read at most every LIST_TTL_SECONDS."""
        with self._lock:
            if not fresh and self._listed and self._monotonic() - self._listed[0] < LIST_TTL_SECONDS:
                return set(self._listed[1])
        envs = self._admin._request("GET", "/_envs").get("envs")
        if not isinstance(envs, list):
            raise AitoError(f"GET /_envs answered without an `envs` list: {str(envs)[:200]}")
        names = {e["name"] for e in envs}
        with self._lock:
            self._listed = (self._monotonic(), names)
        return set(names)

    def live(self) -> list[str]:
        return sorted(n for n in self.names(fresh=True) if is_branch_name(n))

    def client(self, name: str) -> AitoClient:
        """The client for one live branch. Raises SandboxEnvError unless `name`
        is a branch name AND the branch exists: never falls back to master."""
        if not is_branch_name(name):
            raise SandboxEnvError(f"{name!r} is not a sandbox name (tmp-YYYY-MM-DD-HH-MM-SS-<16 hex>)")
        # A branch created a moment ago may not be in the cached list yet.
        exists = name in self.names() or name in self.names(fresh=True)
        if not exists:
            raise SandboxEnvError(f"No sandbox {name}: it expired or never existed. Start a new one.")
        with self._lock:
            if name not in self._clients:
                self._clients[name] = AitoClient(replace(self._admin._config, aito_env=name), writes=WRITES_ANY)
            client = self._clients[name]
            now = self._monotonic()
            resumed = now - self._last_used.get(name, float("-inf")) > RESUME_AFTER_SECONDS
            self._last_used[name] = now
        if resumed and self._on_resume is not None:
            threading.Thread(target=self._on_resume, args=(client,), name=f"resume-{name}", daemon=True).start()
        return client

    def create(self) -> str:
        """A new branch of the template. Raises SandboxFullError at MAX_LIVE,
        counted after reaping the expired ones."""
        self.reap()
        live = self.live()
        if len(live) >= MAX_LIVE:
            oldest = min(expires_at(n) for n in live)
            raise SandboxFullError(f"{len(live)} sandboxes are live, the most there can be; the oldest "
                                   f"expires at {oldest:%H:%M} UTC")
        name = new_branch_name(self._clock())
        self._admin._request("POST", "/_envs", json={"name": name, "basedOn": TEMPLATE})
        if name not in self.names(fresh=True):
            raise AitoError(f"Created sandbox {name}, but the env list doesn't hold it")
        return name

    def delete(self, name: str) -> None:
        """Delete one branch now: "New sandbox" drops the one it replaces, since
        Aito caps how many envs it keeps in memory. Only a branch name is deleted."""
        if not is_branch_name(name):
            raise SandboxEnvError(f"Refusing to delete {name!r}: not a sandbox branch name")
        self._admin._request("DELETE", f"/_envs/{name}")
        with self._lock:
            self._clients.pop(name, None)
            self._last_used.pop(name, None)
        self.names(fresh=True)

    def reap(self) -> list[str]:
        """Delete the branches older than MAX_AGE; returns their names. Any env
        whose name isn't a branch name is left alone, and a `tmp-` one is logged."""
        now = self._clock()
        reaped = []
        for name in sorted(self.names(fresh=True)):
            if not is_branch_name(name):
                if name.startswith("tmp-"):
                    logger.error("Sandbox env %r has a malformed name; not deleting it", name)
                continue
            if now - created_at(name) > MAX_AGE:
                self.delete(name)
                reaped.append(name)
        return reaped

    def reap_forever(self, *, interval: float = 600.0, sleep=time.sleep) -> None:
        while True:
            try:
                for name in self.reap():
                    logger.warning("Reaped sandbox %s (older than %s)", name, MAX_AGE)
            except AitoError as exc:
                logger.error("Sandbox reaper failed; retrying in %.0f s: %s", interval, exc)
            sleep(interval)
