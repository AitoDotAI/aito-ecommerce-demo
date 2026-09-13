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
    # And it back-fills the in-memory layer for the next read — under the
    # namespaced key, since an entry belongs to one backend.
    assert cache._scoped("k") in cache._cache


def test_get_treats_expired_persisted_entry_as_miss():
    # Row exists but expired 60 s ago — must NOT be served. This is the
    # bug that kept stale (and cross-contaminated) entries alive forever.
    cache._aito_client = FakeAitoClient(search_hit=_row({"hits": ["stale"]}, _iso(-60)))
    assert cache.get("k") is None


def test_get_prefers_unexpired_memory_layer():
    import time
    cache._aito_client = FakeAitoClient(search_hit=_row({"v": "aito"}, _iso(300)))
    # Seed L1 directly (no persist thread, so the request count is stable).
    cache._cache[cache._scoped("k")] = (time.monotonic() + 300, {"v": "memory"})
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


# ── Namespacing: a cached answer belongs to ONE backend ──────────────


def test_entries_are_scoped_per_api_version_and_env(monkeypatch):
    """The bug this prevents: v1 and v2 answer the same question
    differently, so a key built from the question alone lets one version
    serve the other's result — silently, because both are well-formed.

    Observed before the fix: a v2 run of "For You" returned a flawless
    all-cat list for a cat owner because it replayed v1's cached entry.
    With the cache bypassed, v2 actually returned cat, dog, dog, dog,
    aquarium. A flip to v2 would have looked correct until each TTL
    expired, then degraded.
    """
    cache.clear()
    cache.set_namespace("v1@master")
    cache.set("for_you:maija:12", {"pets": ["cat"] * 5})

    cache.set_namespace("v2@v2")
    assert cache.get("for_you:maija:12") is None, (
        "v2 must not read v1's entry"
    )

    cache.set("for_you:maija:12", {"pets": ["cat", "dog", "dog"]})
    assert cache.get("for_you:maija:12") == {"pets": ["cat", "dog", "dog"]}

    # ...and writing under v2 must not have clobbered v1's answer.
    cache.set_namespace("v1@master")
    assert cache.get("for_you:maija:12") == {"pets": ["cat"] * 5}
    cache.set_namespace(None)
    cache.clear()


def test_lazy_namespace_matches_the_config_property(monkeypatch):
    """`cache` derives the namespace from the environment when startup
    has not set one (PUBLIC_DEMO / memory-only / tests). That duplicates
    `Config.api_namespace`, so pin them together — if they drift, cache
    entries silently land in the wrong namespace."""
    from src.config import Config

    cache.set_namespace(None)
    cfg_kwargs = dict(aito_api_url="https://x", aito_api_key="k", public_demo=False)

    monkeypatch.delenv("AITO_USE_V2", raising=False)
    monkeypatch.delenv("AITO_ENV", raising=False)
    assert cache._current_namespace() == Config(**cfg_kwargs).api_namespace

    monkeypatch.setenv("AITO_USE_V2", "1")
    expected = Config(**cfg_kwargs, use_v2=True, aito_env="v2").api_namespace
    assert cache._current_namespace() == expected

    monkeypatch.setenv("AITO_ENV", "pr-42")
    expected = Config(**cfg_kwargs, use_v2=True, aito_env="pr-42").api_namespace
    assert cache._current_namespace() == expected
