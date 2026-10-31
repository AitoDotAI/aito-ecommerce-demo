"""Precompute driver — snapshot the precompute-served views offline.

Single source of truth for *which* endpoints are precompute-and-served
(vs. lazily cached by `src/cache.py`). Called from `./do precompute`
and, chained, from `./do reset-data` so a snapshot can never drift
behind a data reload.

For each view it computes the result once (capturing the per-call Aito
timings for the latency pill), writes the `{data, timings}` wrapper to
the Aito `precompute_entries` table, and writes the git-committed JSON
bootstrap at `data/precomputed/{version}-{env}/{name}.json` — snapshots
are scoped to the backend that produced them (see precompute_store).

The Aito write is best-effort — on a read-only key it is skipped with a
warning, but the JSON bootstrap is always written so the committed
fallback stays current. See ADR 0024 and `src/precompute_store.py`.
"""

from __future__ import annotations

import time

from src.aito_client import AitoClient, AitoError
from src import precompute_store as store
from src.overview_service import get_overview
from src.demand_service import get_demand
from src.retention_service import get_retention
from src.supply_service import get_supply


# The views served from precompute snapshots. All are parameterless — a
# single canonical result — which is what makes them precomputable (the
# other light views, For You / Smart Search, vary by persona/query).
#
# The heavy ones each run an `_evaluate` and/or a large fan-out, 14–32 s
# cold; Retention scores every active customer (~2,000 `_predict`s, batched).
# `overview` is light but is the *landing*
# view, so its cold cost is the first thing every visitor would feel —
# precompute it too so the entry page is instant even on a cold, read-
# only public container. See ADR 0024.
#
# The Overview comes last: it quotes Supply's and Retention's decision lines from their
# snapshots, so it must be computed after they are refreshed.
PRECOMPUTED_ENDPOINTS = [
    ("demand",     lambda c: get_demand(c).to_dict()),
    ("retention",  lambda c: get_retention(c).to_dict()),
    ("supply",     lambda c: get_supply(c).to_dict()),
    ("overview",   get_overview),
]


def precompute_all(client: AitoClient, *, verbose: bool = True, write_as_env: str | None = None,
                   files_only: bool = False, only: tuple[str, ...] | None = None) -> None:
    """Snapshot every precompute-served view into Aito + the git bootstrap.

    Runs sequentially: the heavy views each fan out internally to ~20
    parallel Aito calls, so stacking them would blow past Aito's
    inFlightWeight ceiling and 429 (same reason `cache_warmup` is
    sequential).

    `write_as_env` files the snapshots under another env's namespace than
    the one computed on. A release computes on its own env as `master`
    (ADR 0035): the promote makes master hold the same rows, so the
    snapshots are master's from the moment it lands. The Aito rows go to
    the computed env's `precompute_entries`, which the promote carries
    onto master with the rest of the env.

    `files_only` writes the committed JSON and nothing to Aito: a refresh that needs no shared write
    (the Aito rows are filed by the next full run). `only` names the views to refresh.
    """
    names = [name for name, _ in PRECOMPUTED_ENDPOINTS]
    if only is not None and (unknown := [n for n in only if n not in names]):
        raise ValueError(f"no such view to precompute: {unknown}; the views are {names}")

    if not client.check_connectivity():
        if verbose:
            print("  Aito unreachable — cannot precompute.")
        return

    store.init(client)
    namespace = client._config.api_namespace
    if write_as_env is not None:
        namespace = f"{client._config.api_version}@{write_as_env}"
        store.set_namespace(namespace)

    if verbose:
        print(f"Precomputing views as {namespace}…")

    for name, compute_fn in PRECOMPUTED_ENDPOINTS:
        if only is not None and name not in only:
            continue
        try:
            t0 = time.perf_counter()
            wrapper = store.capture(lambda: compute_fn(client))
            ms = int((time.perf_counter() - t0) * 1000)

            # JSON bootstrap first (always), then Aito (best-effort) so a
            # read-only key still refreshes the committed fallback.
            store.write_bootstrap(name, wrapper)
            store.prime(name, wrapper)
            aito_note = "  [files only]" if files_only else ""
            if not files_only:
                try:
                    store.put(name, wrapper)
                except (AitoError, RuntimeError) as exc:
                    aito_note = f"  [Aito write skipped: {exc}]"

            if verbose:
                calls = len(wrapper["timings"])
                print(f"  snapshot: {name:12s} ({ms} ms, {calls} timed calls){aito_note}")
        except Exception as exc:
            if verbose:
                print(f"  snapshot ERR {name}: {exc}")

    if verbose:
        print("Precompute done.")
