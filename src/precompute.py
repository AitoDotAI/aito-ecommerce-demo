"""Precompute driver — snapshot the precompute-served views offline.

Single source of truth for *which* endpoints are precompute-and-served
(vs. lazily cached by `src/cache.py`). Called from `./do precompute`
and, chained, from `./do reset-data` so a snapshot can never drift
behind a data reload.

For each view it computes the result once (capturing the per-call Aito
timings for the latency pill), writes the `{data, timings}` wrapper to
the Aito `precompute_entries` table, and writes the git-committed JSON
bootstrap at `data/precomputed/{name}.json`.

The Aito write is best-effort — on a read-only key it is skipped with a
warning, but the JSON bootstrap is always written so the committed
fallback stays current. See ADR 0024 and `src/precompute_store.py`.
"""

from __future__ import annotations

import time

from src.aito_client import AitoClient, AitoError
from src import precompute_store as store
from src.overview_service import get_dashboard
from src.churn_service import get_churn
from src.demand_service import get_demand
from src.eval_service import run_evaluation
from src.inventory_service import get_inventory
from src.markdown_service import get_markdowns
from src.winback_service import get_winback


# The views served from precompute snapshots. All are parameterless — a
# single canonical result — which is what makes them precomputable (the
# other light views, For You / Smart Search, vary by persona/query).
#
# The six heavy ones (churn … winback) each run an `_evaluate` and/or a
# large fan-out, 14–32 s cold. `dashboard` is light but is the *landing*
# view, so its cold cost is the first thing every visitor would feel —
# precompute it too so the entry page is instant even on a cold, read-
# only public container. See ADR 0024.
PRECOMPUTED_ENDPOINTS = [
    ("dashboard",  lambda c: get_dashboard(c).to_dict()),
    ("churn",      lambda c: get_churn(c).to_dict()),
    ("demand",     lambda c: get_demand(c).to_dict()),
    ("evaluation", lambda c: run_evaluation(c).to_dict()),
    ("inventory",  lambda c: get_inventory(c).to_dict()),
    ("markdown",   lambda c: get_markdowns(c).to_dict()),
    ("winback",    lambda c: get_winback(c).to_dict()),
]


def precompute_all(client: AitoClient, *, verbose: bool = True) -> None:
    """Snapshot every precompute-served view into Aito + the git bootstrap.

    Runs sequentially: the heavy views each fan out internally to ~20
    parallel Aito calls, so stacking them would blow past Aito's
    inFlightWeight ceiling and 429 (same reason `cache_warmup` is
    sequential).
    """
    if not client.check_connectivity():
        if verbose:
            print("  Aito unreachable — cannot precompute.")
        return

    store.init(client)

    if verbose:
        print("Precomputing views…")

    for name, compute_fn in PRECOMPUTED_ENDPOINTS:
        try:
            t0 = time.perf_counter()
            wrapper = store.capture(lambda: compute_fn(client))
            ms = int((time.perf_counter() - t0) * 1000)

            # JSON bootstrap first (always), then Aito (best-effort) so a
            # read-only key still refreshes the committed fallback.
            store.write_bootstrap(name, wrapper)
            aito_note = ""
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
