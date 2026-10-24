"""The app waits for its data (ADR 0035).

A `DataReleaseGate` compares the live row counts with the release file.
These tests drive it with an injected count reader, so they read as the
cutover's and the rollback's timelines: pending until the promote lands,
ready (and warmed) once it does, pending again (and forgotten) if the
data changes under a running app.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.aito_client import AitoError
from src.data_release_gate import DataReleaseGate, is_data_route, release_gate_middleware
from src.release_file import Release

RELEASE = Release(env="observable", counts={"orders": 11909, "contexts": 12662})
RELEASE_DATA = {"orders": 11909, "contexts": 12662}
OLD_DATA = {"orders": 11919, "price_history": 15792}


class Timeline:
    """The data the env holds, changed by the test, and what the gate did."""

    def __init__(self, data: dict[str, int] | Exception):
        self.data = data
        self.events: list[str] = []

    def read_counts(self) -> dict[str, int]:
        if isinstance(self.data, Exception):
            raise self.data
        return dict(self.data)

    def gate(self) -> DataReleaseGate:
        return DataReleaseGate(
            RELEASE,
            read_counts=self.read_counts,
            on_ready=lambda: self.events.append("warm caches"),
            on_mismatch=lambda: self.events.append("drop memory caches"),
        )


# ── The cutover ───────────────────────────────────────────────────


def test_the_gate_is_pending_before_its_first_check():
    gate = Timeline(RELEASE_DATA).gate()
    assert gate.state == "pending"
    assert not gate.is_ready


def test_new_code_on_old_data_stays_pending_and_says_what_differs():
    timeline = Timeline(OLD_DATA)
    gate = timeline.gate()

    gate.check()

    assert gate.state == "pending"
    assert gate.status()["differences"] == [
        "contexts: missing (release has 12662 rows)",
        "orders: 11919 rows, release has 11909",
        "price_history: not in the release (15792 rows)",
    ]
    assert timeline.events == []   # nothing warmed on the old data


def test_after_the_promote_the_gate_turns_ready_and_warms_once():
    timeline = Timeline(OLD_DATA)
    gate = timeline.gate()
    gate.check()

    timeline.data = RELEASE_DATA   # the promote lands
    gate.check()
    gate.check()                   # still matching: no second warm-up

    assert gate.state == "ready"
    assert gate.status()["differences"] == []
    assert timeline.events == ["warm caches"]


# ── The rollback ──────────────────────────────────────────────────


def test_when_the_data_changes_under_a_ready_app_it_forgets_and_waits():
    timeline = Timeline(RELEASE_DATA)
    gate = timeline.gate()
    gate.check()

    timeline.data = OLD_DATA       # the backup is promoted back
    gate.check()

    assert gate.state == "pending"
    assert timeline.events == ["warm caches", "drop memory caches"]


def test_a_failed_read_keeps_the_state_and_reports_the_error():
    timeline = Timeline(RELEASE_DATA)
    gate = timeline.gate()
    gate.check()

    timeline.data = AitoError("Aito request failed: POST /_search: timed out")
    gate.check()

    # One failed read is not evidence that the data changed.
    assert gate.state == "ready"
    assert gate.status()["last_error"] == "Aito request failed: POST /_search: timed out"
    assert timeline.events == ["warm caches"]


def test_run_forever_checks_then_sleeps_the_interval():
    timeline = Timeline(RELEASE_DATA)
    gate = timeline.gate()
    sleeps: list[float] = []

    class Stop(Exception):
        pass

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if len(sleeps) == 2:
            raise Stop

    with pytest.raises(Stop):
        gate.run_forever(sleep=sleep)

    assert sleeps == [60, 60]
    assert gate.state == "ready"


# ── Which routes wait ─────────────────────────────────────────────


@pytest.mark.parametrize("path, gated", [
    ("/api/overview", True),
    ("/api/shop/grid", True),
    ("/api/schema", True),
    ("/api/version", False),
    ("/api/health", False),
    ("/api/uci/draft", False),   # env uci; a pet shop release doesn't touch it
    ("/health", False),
    ("/index.html", False),
])
def test_only_data_routes_wait_for_the_release(path, gated):
    assert is_data_route(path) is gated


def _app_with(gate: DataReleaseGate) -> TestClient:
    app = FastAPI()
    app.middleware("http")(release_gate_middleware(gate))
    app.get("/api/overview")(lambda: {"kpis": []})
    app.get("/api/version")(lambda: {"build": "abc123"})
    return TestClient(app)


def test_a_pending_app_answers_503_on_data_routes_and_version_as_usual():
    gate = Timeline(OLD_DATA).gate()
    gate.check()
    client = _app_with(gate)

    overview = client.get("/api/overview")
    assert overview.status_code == 503
    assert overview.headers["Retry-After"] == "60"
    body = overview.json()
    assert body["error"] == "data release pending"
    assert body["release_env"] == "observable"
    assert "orders: 11919 rows, release has 11909" in body["differences"]

    assert client.get("/api/version").json() == {"build": "abc123"}


def test_a_ready_app_serves_data_routes():
    gate = Timeline(RELEASE_DATA).gate()
    gate.check()

    assert _app_with(gate).get("/api/overview").json() == {"kpis": []}
