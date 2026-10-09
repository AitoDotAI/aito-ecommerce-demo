"""Offline tests for the precompute-and-serve store (ADR 0024).

Covers the read fall-through (L1 → Aito → git JSON → None), the
upsert write, and the two behaviours that make the latency pill honest:
`capture` records real per-call timings at snapshot time, and `serve`
replays them onto the request when serving a precomputed hit. Uses a
fake Aito client; no live DB.
"""

from __future__ import annotations

import json

import pytest

from src import precompute_store as store
from src import timing
from src.aito_client import AitoError


class FakeAito:
    """Records requests; returns canned `_search` hits if seeded.

    `search_hit` seeds one row; `search_hits` seeds several (a table that
    holds stale duplicates of one name). `fail_delete` makes the
    delete-by-name raise, as Aito's `/data/_delete` does when it matches
    rows (HTTP 500).
    """

    def __init__(
        self,
        search_hit: dict | None = None,
        search_hits: list[dict] | None = None,
        fail_delete: bool = False,
    ):
        self.search_hits = search_hits if search_hits is not None else (
            [{"computed_at": 1, **search_hit}] if search_hit else []
        )
        self.fail_delete = fail_delete
        self.requests: list[tuple] = []

    def search(self, table, *, where=None, limit=10):
        self.requests.append(("search", table, where))
        # The real AitoClient records every call on the timing bucket;
        # mimic that so tests can assert the store's own lookup is kept
        # off the latency pill.
        timing.record_call("_search", 9.9)
        return {"hits": self.search_hits}

    def _request(self, method, path, json=None):
        self.requests.append((method, path, json))
        if self.fail_delete and path == "/data/_delete":
            raise AitoError("Aito returned 500 for POST /data/_delete", status_code=500)
        return {}

    def get_schema(self):
        return {"schema": {}}


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Clean module state per test; JSON bootstrap dir points at an
    empty tmp so no test accidentally reads a committed fallback."""
    store._l1.clear()
    saved = store._aito
    monkeypatch.setattr(store, "_FALLBACK_DIR", tmp_path)
    # Snapshots are scoped per backend; pin one so the scoped keys and
    # the namespaced bootstrap directory are deterministic here.
    store.set_namespace("v1@master")
    timing.start_request()  # fresh, empty timing bucket
    yield
    store._l1.clear()
    store.set_namespace(None)
    store._aito = saved


# ── Read fall-through ─────────────────────────────────────────────


def test_get_prefers_l1_over_aito():
    store._l1[store._scoped("churn")] = {"data": {"v": "memory"}}
    store._aito = FakeAito(search_hit={"payload": json.dumps({"data": {"v": "aito"}})})
    assert store.get("churn") == {"data": {"v": "memory"}}
    # L1 hit must short-circuit before any Aito read.
    assert store._aito.requests == []


def test_get_reads_aito_and_backfills_l1():
    store._aito = FakeAito(search_hit={"payload": json.dumps({"data": {"v": 1}})})
    assert store.get("churn") == {"data": {"v": 1}}
    # Next read serves from L1 without touching Aito again.
    assert store._l1[store._scoped("churn")] == {"data": {"v": 1}}


def test_get_serves_the_newest_row_when_stale_duplicates_exist():
    # Aito's delete can fail, leaving the previous snapshot beside the new
    # one. The reader must not depend on which row the search returns first.
    def row(computed_at: int, marker: str) -> dict:
        return {"computed_at": computed_at, "payload": json.dumps({"data": {"v": marker}})}

    store._aito = FakeAito(search_hits=[row(100, "stale"), row(300, "newest"), row(200, "older")])
    assert store.get("churn") == {"data": {"v": "newest"}}


def test_get_falls_back_to_committed_json(tmp_path):
    # Aito misses (no hit); the committed JSON bootstrap serves.
    ns_dir = tmp_path / "v1-master"
    ns_dir.mkdir(parents=True, exist_ok=True)
    (ns_dir / "churn.json").write_text(json.dumps({"data": {"v": "json"}}))
    store._aito = FakeAito(search_hit=None)
    assert store.get("churn") == {"data": {"v": "json"}}


def test_get_returns_none_on_total_miss():
    store._aito = FakeAito(search_hit=None)
    assert store.get("nope") is None


# ── Write ─────────────────────────────────────────────────────────


def test_put_upserts_delete_then_insert():
    store._aito = FakeAito()
    store.put("churn", {"data": {"x": 1}, "timings": []})
    paths = [(m, p) for (m, p, _) in store._aito.requests]
    # Delete-by-name precedes the insert (one row per name, not append).
    assert paths == [
        ("POST", "/data/_delete"),
        ("POST", "/data/precompute_entries"),
    ]
    # The stored name carries the backend that produced the snapshot, so
    # a v2 deployment cannot serve a v1-computed entry.
    assert store._aito.requests[0][2]["where"]["name"] == "v1@master|churn"
    insert_body = store._aito.requests[1][2]
    assert insert_body["name"] == "v1@master|churn"
    assert isinstance(insert_body["computed_at"], int)
    # payload is a JSON string round-tripping to the wrapper.
    assert json.loads(insert_body["payload"]) == {"data": {"x": 1}, "timings": []}
    # L1 is refreshed so the writing process sees the new value.
    assert store._l1[store._scoped("churn")] == {"data": {"x": 1}, "timings": []}


def test_put_reports_a_failed_delete_and_still_inserts(caplog):
    # Aito answers 500 when `_delete` matches rows. The failure used to be
    # swallowed, so stale rows piled up unnoticed; it must be reported.
    store._aito = FakeAito(fail_delete=True)
    with caplog.at_level("WARNING", logger="src.precompute_store"):
        store.put("churn", {"data": {"x": 1}, "timings": []})
    assert "v1@master|churn" in caplog.text
    assert "500" in caplog.text
    assert [(m, p) for (m, p, _) in store._aito.requests][-1] == ("POST", "/data/precompute_entries")


# ── Latency-pill honesty: capture + serve ─────────────────────────


def test_capture_wraps_data_with_real_timings():
    def compute():
        # Simulate the Aito calls a heavy endpoint makes at compute time.
        timing.record_call("/_evaluate", 15515.0)
        timing.record_call("/_search", 4.2)
        return {"accuracy": 0.95}

    wrapper = store.capture(compute)
    assert wrapper["data"] == {"accuracy": 0.95}
    # Timings are captured with the leading slash stripped, ready to
    # re-emit on the X-Aito-Calls header.
    assert wrapper["timings"] == [("_evaluate", 15515.0), ("_search", 4.2)]


def test_serve_replays_timings_from_store_hit():
    store._l1[store._scoped("churn")] = {
        "data": {"kpis": {"at_risk": 12}},
        "timings": [["_evaluate", 15515.0]],
    }
    result = store.serve("churn", lambda: pytest.fail("must not compute on a hit"))
    assert result == {"kpis": {"at_risk": 12}}
    # The recorded query cost is replayed onto the request so the pill
    # shows the real _evaluate time, not a blank "cached" pill.
    assert timing.current_calls() == [("_evaluate", 15515.0)]


def test_serve_keeps_the_store_lookup_off_the_pill():
    # An Aito-backed hit: `get` runs an `_search` to precompute_entries,
    # which the client records. That cache-read must not appear on the
    # pill — only the snapshot's own query timings.
    hit = {"payload": json.dumps({"data": {"x": 1}, "timings": [["_evaluate", 100.0]]})}
    store._aito = FakeAito(search_hit=hit)
    result = store.serve("churn", lambda: pytest.fail("must not compute on a hit"))
    assert result == {"x": 1}
    assert timing.current_calls() == [("_evaluate", 100.0)]  # no stray _search


def test_replace_calls_mutates_the_bucket_in_place():
    # The pill survives FastAPI's sync-endpoint threadpool only because
    # the middleware and endpoint share ONE bucket list object. If
    # `replace_calls` rebinds the ContextVar instead of mutating in
    # place, the replayed timings never reach the header. Pin the list
    # identity so a reassign regression fails here, not in prod.
    timing.start_request()
    bucket = timing._calls.get()
    timing.record_call("_search", 9.9)  # the store lookup
    timing.replace_calls([("_evaluate", 100.0)])
    assert timing._calls.get() is bucket  # same object, not a rebind
    assert timing.current_calls() == [("_evaluate", 100.0)]


def test_serve_falls_back_to_live_compute_on_miss():
    store._aito = FakeAito(search_hit=None)  # no Aito row, empty JSON dir
    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return {"live": True}

    assert store.serve("churn", compute) == {"live": True}
    assert calls["n"] == 1


# ── Namespacing: a snapshot belongs to the backend that computed it ──


def test_a_v1_snapshot_is_not_served_under_v2(tmp_path):
    """Seven views serve from this store, and unlike the cache these
    entries have no TTL and are committed to git — so an unscoped
    snapshot would make a v2 deployment render v1's numbers
    indefinitely, fast and wrong, with nothing on screen to say so.
    """
    store._aito = None  # L1 + committed-JSON path only
    store.set_namespace("v1@master")
    store._l1[store._scoped("churn")] = {"data": {"engine": "v1"}, "timings": []}

    store.set_namespace("v2@v2")
    assert store.get("churn") is None, "v2 must not read v1's snapshot"

    # And each keeps its own.
    store._l1[store._scoped("churn")] = {"data": {"engine": "v2"}, "timings": []}
    assert store.get("churn")["data"] == {"engine": "v2"}
    store.set_namespace("v1@master")
    assert store.get("churn")["data"] == {"engine": "v1"}


def test_bootstrap_json_is_written_per_namespace(tmp_path, monkeypatch):
    """The committed fallback is per backend — `data/precomputed/
    v1-master/churn.json` — so v1's and v2's snapshots can coexist in
    the repo instead of overwriting each other."""
    monkeypatch.setattr(store, "_FALLBACK_DIR", tmp_path)
    store.set_namespace("v2@v2")
    store.write_bootstrap("churn", {"data": {"engine": "v2"}, "timings": []})
    assert (tmp_path / "v2-v2" / "churn.json").is_file()

    store.set_namespace("v1@master")
    store.write_bootstrap("churn", {"data": {"engine": "v1"}, "timings": []})
    assert (tmp_path / "v1-master" / "churn.json").is_file()

    store.set_namespace(None)


def test_namespace_fallback_matches_the_config_property(monkeypatch):
    from src.config import Config, current_api_namespace

    store.set_namespace(None)
    monkeypatch.setenv("AITO_USE_V2", "1")
    cfg = Config(aito_api_url="https://x", aito_api_key="k", public_demo=False,
                 use_v2=True, aito_env="master")
    assert store._current_namespace() == cfg.api_namespace == current_api_namespace()
