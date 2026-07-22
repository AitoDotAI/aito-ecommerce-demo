"""Precompute-and-serve store for the demo's parameterless views.

Seven views are served from offline snapshots: the six heavy ones
(churn, demand, evaluation, inventory, markdown, winback) plus the
dashboard landing page (light-looking, but ~321 sequential `_search`
calls / ~93 s cold — the heaviest cold page, and the first one every
visitor loads; see ADR 0024).

The heavy views each run an `_evaluate` and/or a large `_predict` /
`_estimate` fan-out. Live, that is 14–32 s on a cold container. Worse,
the public
deploy runs a **read-only** API key, so `src/cache.py`'s write-through
L2 layer is disabled there — every restart starts cold and the startup
warmup has to recompute all six.

This module inverts the write path. The heavy work runs **offline** in
`./do precompute` (see `src/precompute.py`), which snapshots each
endpoint's result into an Aito `precompute_entries` table. The running
container only ever **reads** — never computes at request time. Reading
needs only a read key, so it works on the public deploy where the lazy
L2 cache cannot.

Read order (`get`):

1. **L1** in-process dict — microsecond access, dropped on restart.
2. **Aito** `precompute_entries` — durable, written by `./do precompute`,
   the source of truth for "current snapshot". A few-hundred-ms read.
3. **Local JSON** at `data/precomputed/{name}.json` — bootstrap
   fallback, committed to git, for two cases: (a) a fresh Aito with no
   precompute table yet; (b) Aito briefly unreachable in production.
4. `None` — caller (`serve`) falls back to live computation.

Writes happen only from `./do precompute` via `snapshot`. Endpoints
never write.

Latency pill: a precomputed read makes no Aito call, so the
`X-Aito-Calls` header would vanish on exactly these pages — losing the
"see how fast the query is" moment. `snapshot` records the per-call
timings measured at compute time and stores them alongside the result;
`serve` replays them onto the request's timing bucket. The pill shows
the *real* query cost from an honest snapshot, not a fabricated number.

Contrast with `src/cache.py`: that is a *lazy* cache for the nine light
endpoints (compute on first hit, write-through, disabled on the public
key). This is a *precompute-and-serve* store for the six heavy ones
(compute offline, read-only at request time). Two mechanisms, one line
between them: heavy/offline here, light/lazy there.

Mirrors `aito-accounting-demo/src/precompute_store.py`.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Callable

from src.aito_client import AitoClient, AitoError
from src import timing

PRECOMPUTE_TABLE = "precompute_entries"
PRECOMPUTE_SCHEMA = {
    "type": "table",
    "columns": {
        "name":        {"type": "String", "nullable": False},
        "payload":     {"type": "Text",   "nullable": False},
        "computed_at": {"type": "Int",    "nullable": False},
    },
}

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_FALLBACK_DIR = _PROJECT_ROOT / "data" / "precomputed"

_aito: AitoClient | None = None
_l1: dict[str, Any] = {}
_l1_mutex = threading.Lock()


# ── Wrapper format ────────────────────────────────────────────────
#
# A stored entry is `{"data": <endpoint payload>, "timings": [[ep, ms],
# ...]}`. The wrapper lives entirely here so the writer (`snapshot`) and
# the reader (`serve`) cannot drift on its shape.


def _fallback_path(name: str) -> Path:
    return _FALLBACK_DIR / f"{name}.json"


def init(client: AitoClient) -> None:
    """Register the client and ensure the table exists. Non-fatal on
    failure — the git-committed JSON bootstrap still serves reads."""
    global _aito
    _aito = client
    try:
        schema = client.get_schema()
        if PRECOMPUTE_TABLE not in schema.get("schema", {}):
            client._request("PUT", f"/schema/{PRECOMPUTE_TABLE}", json=PRECOMPUTE_SCHEMA)
    except AitoError:
        # Read-only key (public deploy) or unreachable Aito: reads still
        # work via the Aito table (if present) and the JSON bootstrap.
        pass


# ── Low-level get / put ───────────────────────────────────────────


def get(name: str) -> Any | None:
    """Read a snapshot entry, falling back L1 → Aito → git JSON → None."""
    cached = _l1.get(name)
    if cached is not None:
        return cached

    if _aito is not None:
        try:
            r = _aito.search(PRECOMPUTE_TABLE, where={"name": name}, limit=1)
            hits = r.get("hits", [])
            if hits:
                value = json.loads(hits[0]["payload"])
                with _l1_mutex:
                    _l1[name] = value
                return value
        except (AitoError, KeyError, json.JSONDecodeError):
            pass  # fall through to the bootstrap file

    path = _fallback_path(name)
    if path.is_file():
        try:
            with open(path) as f:
                value = json.load(f)
            with _l1_mutex:
                _l1[name] = value
            return value
        except (OSError, json.JSONDecodeError):
            pass

    return None


def put(name: str, value: Any) -> None:
    """Upsert one snapshot entry into Aito. Caller is `./do precompute`.

    Raises `AitoError` so the precompute driver can tell "wrote" from
    "failed". No native upsert primitive yet, so delete-by-name then
    insert keeps the table at one row per name.
    """
    if _aito is None:
        raise RuntimeError("precompute_store.init() not called")
    payload = json.dumps(value, ensure_ascii=False, default=str)
    try:
        _aito._request(
            "POST", "/data/_delete",
            json={"from": PRECOMPUTE_TABLE, "where": {"name": name}},
        )
    except AitoError:
        # Best-effort: a first-time write has nothing to delete.
        pass
    _aito._request(
        "POST", f"/data/{PRECOMPUTE_TABLE}",
        json={"name": name, "payload": payload, "computed_at": int(time.time())},
    )
    with _l1_mutex:
        _l1[name] = value


def write_bootstrap(name: str, value: Any) -> None:
    """Write the git-committed JSON fallback for `name`."""
    _FALLBACK_DIR.mkdir(parents=True, exist_ok=True)
    with open(_fallback_path(name), "w") as f:
        json.dump(value, f, ensure_ascii=False, indent=2, default=str)


# ── Snapshot (writer) and serve (reader) ──────────────────────────


def capture(compute_fn: Callable[[], Any]) -> dict:
    """Compute `compute_fn` once under a fresh timing bucket and return
    the `{data, timings}` wrapper. Pure — no persistence; the caller
    (`src/precompute.py`) decides how to store it.

    Run from `./do precompute` in a process that has NOT initialised the
    lazy persistent cache, so `compute_fn` always computes live (never a
    cache hit) and the captured timings are real.
    """
    timing.start_request()
    data = compute_fn()
    timings = timing.current_calls()
    return {"data": data, "timings": timings}


def serve(name: str, compute_fn: Callable[[], Any]) -> Any:
    """Return the precomputed result for `name`, replaying its recorded
    timings onto the current request's pill. On a store miss (fresh
    local dev with no snapshot), fall back to live `compute_fn`.
    """
    before = timing.current_calls()
    entry = get(name)
    if isinstance(entry, dict) and "data" in entry:
        # Drop the store's own precompute_entries lookup (an Aito
        # `_search` recorded during `get`) so the pill shows the
        # snapshot's real query cost, not the cache read that served it.
        timing.replace_calls(before)
        for ep, ms in entry.get("timings", []):
            timing.record_call(ep, ms)
        return entry["data"]
    return compute_fn()


def invalidate(name: str | None = None) -> None:
    """Drop L1 for one name, or everything when `name` is None."""
    with _l1_mutex:
        if name is None:
            _l1.clear()
        else:
            _l1.pop(name, None)
