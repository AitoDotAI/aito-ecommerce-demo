"""`/api/health` makes the data release gate check again when its last check is over a minute old (ADR 0035, amended 2026-10-31).

Importing the app starts the release gate's polling thread and the cache warmup, which read the shared Aito.
`AITO_SKIP_STARTUP_WARMUP=1` leaves both out so the route can be driven offline.
"""

from __future__ import annotations

import importlib
import sys

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_module(monkeypatch):
    monkeypatch.setenv("AITO_SKIP_STARTUP_WARMUP", "1")
    monkeypatch.setenv("AITO_API_URL", "https://example.invalid")
    monkeypatch.setenv("AITO_API_KEY", "not-a-real-key")
    sys.modules.pop("src.app", None)
    module = importlib.import_module("src.app")
    yield module
    sys.modules.pop("src.app", None)


def test_importing_the_app_with_the_skip_switch_starts_no_gate_thread(app_module):
    assert app_module.release_gate.state == "pending"
    assert app_module.release_gate.differences == ["not checked yet"]


def test_a_health_probe_checks_the_release_when_the_last_check_is_over_a_minute_old(app_module, monkeypatch):
    now = [5000.0]
    reads: list[int] = []
    gate = app_module.release_gate
    monkeypatch.setattr(gate, "_clock", lambda: now[0])
    monkeypatch.setattr(gate, "_read_counts", lambda: reads.append(1) or {})
    monkeypatch.setattr(app_module.cache, "get", lambda key: {"status": "ok"})
    client = TestClient(app_module.app)

    client.get("/api/health")
    now[0] += 30
    client.get("/api/health")
    now[0] += 31
    client.get("/api/health")

    assert len(reads) == 2, "the first probe checks, the second (30 s later) does not, the third (61 s later) does"


def test_the_health_answer_carries_the_gate_state_the_probe_just_read(app_module, monkeypatch):
    gate = app_module.release_gate
    monkeypatch.setattr(gate, "_read_counts", lambda: dict(gate.release.counts))
    monkeypatch.setattr(gate, "_on_ready", lambda: None)
    monkeypatch.setattr(app_module.cache, "get", lambda key: {"status": "ok"})

    body = TestClient(app_module.app).get("/api/health").json()

    assert body["data_release"]["state"] == "ready"
