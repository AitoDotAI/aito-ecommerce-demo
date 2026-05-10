"""Two-layer cache: in-memory for speed, Aito for persistence.

Layer 1: In-memory dict with TTL — instant reads, cleared on restart.
Layer 2: Aito `prediction_cache` table — survives restarts, analyzable
via `_relate`, and demonstrates Aito as both prediction engine and
prediction store.

On get: check memory → check Aito → miss.
On set: write to memory AND to Aito (background thread).

Single-tenant: one Aito client, one keyspace. Multi-tenant
partitioning was dropped vs. `aito-erp-demo`; restore it from there if
you ever need per-tenant isolation again.

Public-demo mode (`PUBLIC_DEMO=1`): the persistent layer is disabled
entirely. `init_persistent_cache` becomes a no-op so we never try to
PUT a schema with a read-only API key, and the in-memory TTL cache is
the only path. Trade-off: cold cache after every restart; the warmup
loop pays the predict cost again. Acceptable for a public demo where
we'd rather not write to Aito at all.
"""

import datetime
import hashlib
import json
import os
import time
import threading
from typing import Any

from src.aito_client import AitoClient, AitoError

PUBLIC_DEMO = os.environ.get("PUBLIC_DEMO", "").lower() in ("1", "true", "yes")

# ── Layer 1: In-memory TTL cache ──────────────────────────────────

_cache: dict[str, tuple[float, Any]] = {}
DEFAULT_TTL = 600  # 10 minutes

# ── Per-key compute lock ─────────────────────────────────────────
#
# Prevents stampede: when the warmup thread is computing a key and a
# user request asks for the same key, the second caller waits on the
# warmup's result instead of racing it with a parallel Aito call.
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(key: str) -> threading.Lock:
    with _locks_guard:
        lock = _locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _locks[key] = lock
        return lock


def get_or_compute(key: str, compute_fn, ttl: int = DEFAULT_TTL) -> Any:
    """Cache-aware compute: return cached value if present, otherwise
    serialise concurrent computations under a per-key lock."""
    cached = get(key)
    if cached is not None:
        return cached
    lock = _lock_for(key)
    with lock:
        cached = get(key)
        if cached is not None:
            return cached
        value = compute_fn()
        set(key, value, ttl=ttl)
        return value


# ── Layer 2: Aito persistent cache ────────────────────────────────

_aito_client: AitoClient | None = None

CACHE_TABLE = "prediction_cache"
CACHE_SCHEMA = {
    "type": "table",
    "columns": {
        "cache_key": {"type": "String", "nullable": False},
        "endpoint": {"type": "String", "nullable": False},
        "response_json": {"type": "String", "nullable": False},
        "created_at": {"type": "String", "nullable": False},
    },
}


def init_persistent_cache(client: AitoClient) -> None:
    """Register the Aito client and ensure the cache table exists.
    Call once at startup.

    No-op in `PUBLIC_DEMO` mode: registering would trip read-only API
    keys and writing the cache row on `set()` would fail anyway. The
    memory-only TTL cache handles a public demo's traffic shape fine.
    """
    global _aito_client
    if PUBLIC_DEMO:
        return

    _aito_client = client

    try:
        schema = client.get_schema()
        if CACHE_TABLE not in schema.get("schema", {}):
            client._request("PUT", f"/schema/{CACHE_TABLE}", json=CACHE_SCHEMA)
            print(f"  Created {CACHE_TABLE} table.")
    except AitoError as e:
        print(f"  Could not create cache table: {e}")


def _key_hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def get(key: str) -> Any | None:
    """Check memory first, then Aito."""
    entry = _cache.get(key)
    if entry is not None:
        expires_at, value = entry
        if time.monotonic() <= expires_at:
            return value
        del _cache[key]

    if _aito_client is not None:
        try:
            result = _aito_client._request(
                "POST", "/_search",
                json={
                    "from": CACHE_TABLE,
                    "where": {"cache_key": _key_hash(key)},
                    "limit": 1,
                },
            )
            hits = result.get("hits", [])
            if hits:
                value = json.loads(hits[0]["response_json"])
                _cache[key] = (time.monotonic() + DEFAULT_TTL, value)
                return value
        except (AitoError, json.JSONDecodeError, KeyError):
            pass

    return None


def set(key: str, value: Any, ttl: int = DEFAULT_TTL) -> None:
    """Write to memory and persist to Aito in background."""
    _cache[key] = (time.monotonic() + ttl, value)

    if _aito_client is not None:
        client = _aito_client

        def persist():
            try:
                record = {
                    "cache_key": _key_hash(key),
                    "endpoint": key.split(":", 1)[0],
                    "response_json": json.dumps(value, default=str),
                    "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                }
                client._request("POST", f"/data/{CACHE_TABLE}", json=record)
            except AitoError:
                pass

        threading.Thread(target=persist, daemon=True).start()


def clear() -> None:
    """Clear in-memory cache only. Aito persistent cache is left intact."""
    _cache.clear()


def clear_all() -> None:
    """Clear in-memory cache + Aito cache table."""
    _cache.clear()
    if _aito_client is not None:
        try:
            _aito_client._request("DELETE", f"/schema/{CACHE_TABLE}")
            _aito_client._request("PUT", f"/schema/{CACHE_TABLE}", json=CACHE_SCHEMA)
            print("Cleared Aito prediction cache.")
        except AitoError as e:
            print(f"Could not clear Aito cache: {e}")
