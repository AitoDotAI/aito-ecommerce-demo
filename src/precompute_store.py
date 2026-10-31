"""Precompute-and-serve store for the demo's parameterless views.

Four views are served from offline snapshots: the heavy ones (demand,
retention, supply; `src/precompute.py` lists them) plus the
Overview landing page (light-looking, but ~321 sequential `_search`
calls / ~93 s cold — the heaviest cold page, and the first one every
visitor loads; see ADR 0024).

The heavy views each run an `_evaluate` and/or a large `_predict` /
`_estimate` fan-out. Live, that is 14–32 s on a cold container. Worse,
the public
deploy runs a **read-only** API key, so `src/cache.py`'s write-through
L2 layer is disabled there — every restart starts cold and the startup
warmup has to recompute them all.

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
key). This is a *precompute-and-serve* store for the heavy ones
(compute offline, read-only at request time). Two mechanisms, one line
between them: heavy/offline here, light/lazy there.

Mirrors `aito-accounting-demo/src/precompute_store.py`.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable

from src.aito_client import AitoClient, AitoError
from src import timing
from src.config import current_api_namespace

logger = logging.getLogger(__name__)

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


# ── Namespacing: a snapshot belongs to the backend that computed it ──
#
# Same reasoning as `src/cache.py`. A precomputed dashboard is an ANSWER,
# and v1/master and v2/<env> answer differently — so a snapshot keyed on
# the view name alone is replayed under whichever API happens to be
# configured. That is worse here than in the cache: these entries have no
# TTL, they are committed to git, and seven views serve from them, so a
# v2 deployment would render v1's numbers indefinitely and look fast
# doing it.
#
# All three layers are scoped: the L1 dict, the `name` column in Aito,
# and the committed JSON (one directory per namespace).

_namespace: str | None = None


def set_namespace(namespace: str | None) -> None:
    """Scope every snapshot to a backend. Called by `init`.

    Deliberately does NOT clear L1: the keys already carry the
    namespace, so entries for different backends coexist rather than
    evicting each other.
    """
    global _namespace
    _namespace = namespace


def _current_namespace() -> str:
    return _namespace if _namespace is not None else current_api_namespace()


def _scoped(name: str, namespace: str | None = None) -> str:
    """Key used for L1 and for the `name` column in Aito."""
    return f"{namespace or _current_namespace()}|{name}"


def _namespace_dir(namespace: str) -> str:
    """`v1@master` -> `v1-master`; `@` is legal in a path but reads
    badly in a repo tree and in shell globs."""
    return namespace.replace("@", "-")


def _fallback_path(name: str, namespace: str | None = None) -> Path:
    return _FALLBACK_DIR / _namespace_dir(namespace or _current_namespace()) / f"{name}.json"


# ── The release env reads the snapshots its release filed for master ──
#
# A release computes its snapshots on the release env and files them as
# master (`./do precompute --as master`, ADR 0035), because after the
# promote master holds the same rows. Before the promote, an app reading
# the release env itself (staging, or `AITO_ENV=observable ./do dev`)
# would find none under its own namespace. Its data is the release's (the
# data release gate checks it), so it reads master's snapshots too, after
# its own. Writes always go to the current namespace.

_release_namespace: str | None = None


def read_release_snapshots(namespace: str | None) -> None:
    """Also read `namespace`'s snapshots on a miss (None: only our own)."""
    global _release_namespace
    _release_namespace = namespace


def release_snapshot_namespace(config, release_env: str) -> str | None:
    """Master's namespace when `config` reads the release env, else None."""
    if config.aito_env == release_env and release_env != "master":
        return f"{config.api_version}@master"
    return None


def init(client: AitoClient) -> None:
    """Register the client and ensure the table exists. Non-fatal on
    failure — the git-committed JSON bootstrap still serves reads."""
    global _aito
    _aito = client
    # Scope snapshots to the backend that produced them, before any read.
    set_namespace(client._config.api_namespace)
    try:
        schema = client.get_schema()
        # A read-only client (ADR 0043) reads the snapshots; it never creates the table.
        if PRECOMPUTE_TABLE not in schema.get("schema", {}) and not client.read_only:
            client._request("PUT", f"/schema/{PRECOMPUTE_TABLE}", json=PRECOMPUTE_SCHEMA)
    except AitoError:
        # Read-only key (public deploy) or unreachable Aito: reads still
        # work via the Aito table (if present) and the JSON bootstrap.
        pass


# ── Low-level get / put ───────────────────────────────────────────


# What a snapshot of a view must hold for the current code to read it. A snapshot filed before a view changed shape (the
# shared Aito keeps the old row until `./do precompute` is run) lacks these and is not served: the committed JSON,
# which ships with the code, is. Without this a deploy would need the precompute run in lockstep.
REQUIRED_KEYS: dict[str, tuple[str, ...]] = {
    "supply": ("planning_month",),     # Supply plans on observed sales (ADR 0041, amended 2026-10-31)
}


def _has_required_keys(name: str, value: Any) -> bool:
    data = value.get("data") if isinstance(value, dict) else None
    return all(isinstance(data, dict) and key in data for key in REQUIRED_KEYS.get(name, ()))


def get(name: str) -> Any | None:
    """Read a snapshot entry, falling back L1 → Aito → git JSON → None.

    On the release env, a miss is read again under master's namespace
    (see `read_release_snapshots`)."""
    found = _get_in(_current_namespace(), name)
    if found is None and _release_namespace and _release_namespace != _current_namespace():
        found = _get_in(_release_namespace, name)
    return found


def _get_in(namespace: str, name: str) -> Any | None:
    key = _scoped(name, namespace)
    cached = _l1.get(key)
    if cached is not None:
        return cached

    if _aito is not None:
        try:
            r = _aito.search(PRECOMPUTE_TABLE, where={"name": key}, limit=10)
            hits = r.get("hits", [])
            if hits:
                # `put`'s delete can fail and leave older snapshots of the
                # same name behind, so take the newest rather than the
                # first hit.
                newest = max(hits, key=lambda hit: hit["computed_at"])
                value = json.loads(newest["payload"])
                if _has_required_keys(name, value):
                    with _l1_mutex:
                        _l1[key] = value
                    return value
        except (AitoError, KeyError, json.JSONDecodeError):
            pass  # fall through to the bootstrap file

    path = _fallback_path(name, namespace)
    if path.is_file():
        try:
            with open(path) as f:
                value = json.load(f)
            with _l1_mutex:
                _l1[key] = value
            return value
        except (OSError, json.JSONDecodeError):
            pass

    return None


def put(name: str, value: Any) -> None:
    """Upsert one snapshot entry into Aito. Caller is `./do precompute`.

    Raises `AitoError` so the precompute driver can tell "wrote" from
    "failed". No native upsert primitive yet, so this deletes by name and
    then inserts. When the delete fails (Aito answers 500 if it matches
    rows) the old row stays, and `get` reads the newest row of the name.
    """
    if _aito is None:
        raise RuntimeError("precompute_store.init() not called")
    key = _scoped(name)
    payload = json.dumps(value, ensure_ascii=False, default=str)
    try:
        _aito._request(
            "POST", "/data/_delete",
            json={"from": PRECOMPUTE_TABLE, "where": {"name": key}},
        )
    except AitoError as exc:
        # A first-time write deletes nothing and succeeds, so an error
        # here is real: Aito answers 500 when `_delete` matches rows. The
        # insert below still goes ahead and `get` reads the newest row,
        # but the old row stays in the table.
        logger.warning(
            "Could not delete the previous snapshot %r (HTTP %s); "
            "stale rows remain in %s: %s",
            key, exc.status_code, PRECOMPUTE_TABLE, exc,
        )
    _aito._request(
        "POST", f"/data/{PRECOMPUTE_TABLE}",
        json={"name": key, "payload": payload, "computed_at": int(time.time())},
    )
    with _l1_mutex:
        _l1[key] = value


def prime(name: str, value: Any) -> None:
    """Make `value` what a later `get(name)` in this process returns, without writing anywhere.
    The precompute driver uses it so a view that quotes another reads the other's new snapshot."""
    with _l1_mutex:
        _l1[_scoped(name)] = value


def write_bootstrap(name: str, value: Any) -> None:
    """Write the git-committed JSON fallback for `name`."""
    path = _fallback_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
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
            _l1.pop(_scoped(name), None)
            if _release_namespace:
                _l1.pop(_scoped(name, _release_namespace), None)
