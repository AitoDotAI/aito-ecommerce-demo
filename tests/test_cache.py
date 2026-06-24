"""Offline tests for the two-layer cache's persistence semantics.

Covers the TTL-honoring read and the upsert write — the two bugs that
let a short-TTL (or pre-reload) entry live forever and let duplicate
rows accumulate per key. Uses a fake Aito client; no live DB.
"""

from __future__ import annotations

import datetime
import json

import pytest

from src import cache


def _iso(offset_seconds: int) -> str:
    """ISO-8601 UTC instant `offset_seconds` from now (negative = past)."""
    return (
        datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(seconds=offset_seconds)
    ).isoformat()


class FakeAitoClient:
    """Records requests; returns a canned `_search` hit if seeded."""

    def __init__(self, search_hit: dict | None = None):
        self.search_hit = search_hit
        self.requests: list[tuple[str, str, dict | None]] = []

    def _request(self, method: str, path: str, json: dict | None = None):
        self.requests.append((method, path, json))
        if path == "/_search":
            return {"hits": [self.search_hit] if self.search_hit else []}
        return {}


@pytest.fixture(autouse=True)
def _isolate_cache():
    """Each test gets a clean module state."""
    cache._cache.clear()
    saved = cache._aito_client
    yield
    cache._cache.clear()
    cache._aito_client = saved


def _row(value, expires_at: str) -> dict:
    return {
        "cache_key": cache._key_hash("k"),
        "endpoint": "smart_search",
        "response_json": json.dumps(value),
        "created_at": _iso(0),
        "expires_at": expires_at,
    }


def test_get_returns_fresh_persisted_entry():
    cache._aito_client = FakeAitoClient(search_hit=_row({"hits": [1, 2]}, _iso(300)))
    assert cache.get("k") == {"hits": [1, 2]}
    # And it back-fills the in-memory layer for the next read.
    assert "k" in cache._cache


def test_get_treats_expired_persisted_entry_as_miss():
    # Row exists but expired 60 s ago — must NOT be served. This is the
    # bug that kept stale (and cross-contaminated) entries alive forever.
    cache._aito_client = FakeAitoClient(search_hit=_row({"hits": ["stale"]}, _iso(-60)))
    assert cache.get("k") is None


def test_get_prefers_unexpired_memory_layer():
    import time
    cache._aito_client = FakeAitoClient(search_hit=_row({"v": "aito"}, _iso(300)))
    # Seed L1 directly (no persist thread, so the request count is stable).
    cache._cache["k"] = (time.monotonic() + 300, {"v": "memory"})
    assert cache.get("k") == {"v": "memory"}
    # Memory hit must short-circuit before any Aito read.
    assert cache._aito_client.requests == []


def test_persist_upserts_delete_then_insert_with_expiry():
    client = FakeAitoClient()
    cache._persist(client, "smart_search:maija:food", {"x": 1}, ttl=300)
    paths = [(m, p) for (m, p, _) in client.requests]
    # Delete-by-key precedes the insert (one row per key, not append).
    assert paths == [("POST", "/data/_delete"), ("POST", "/data/prediction_cache")]
    delete_body = client.requests[0][2]
    assert delete_body == {
        "from": "prediction_cache",
        "where": {"cache_key": cache._key_hash("smart_search:maija:food")},
    }
    insert_body = client.requests[1][2]
    assert insert_body["endpoint"] == "smart_search"
    # expires_at is in the future and after created_at.
    assert insert_body["expires_at"] > insert_body["created_at"]
