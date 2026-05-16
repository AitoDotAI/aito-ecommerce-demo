"""Cache warmup — pre-compute every cacheable endpoint once.

Single source of truth for "what to warm" and "in what order".
Called from two sites:

  - `src/app.py` on import — kicks off a daemon thread that calls
    `warm_all(client)` so the server stays responsive while
    warmup runs in the background.
  - `./do reset-data` — calls `warm_all(client)` synchronously
    after the data upload completes. This populates the L2
    `prediction_cache` Aito table so the next `./do dev` boot is
    fast even on the very first request.

Without the latter, the first boot after `reset-data` hits cold
endpoints — Churn alone takes ~22 s on the first user request.
With it, every endpoint is warm before the dev server even
starts.
"""

from __future__ import annotations

import time

from src.aito_client import AitoClient
from src.overview_service import get_dashboard
from src.search_service import smart_search
from src.recommend_service import get_for_you
from src.bought_together_service import get_bought_together
from src.filling_service import get_filling
from src.eval_service import run_evaluation
from src.analytics_service import get_analytics
from src.pattern_service import get_patterns
from src.feedback_service import get_feedback
from src.churn_service import get_churn
from src.demand_service import get_demand
from src.inventory_service import get_inventory
from src.price_service import get_prices


def warm_all(client: AitoClient, *, verbose: bool = True) -> None:
    """Pre-compute every cacheable endpoint once.

    Order: cheap endpoints first, then the four slowest. Each
    service's `cache.set(...)` populates both the in-memory L1
    and the Aito-backed L2 layer, so subsequent process restarts
    find the L2 already warm and L1 fills again on this same
    boot's request path.

    Everything runs sequentially: `evaluation` and the
    `_estimate`-heavy endpoints each fan out internally to ~20
    parallel Aito calls, so stacking *them* in parallel here
    blows past Aito's `inFlightWeight` capacity (48) and yields
    429 server-overloaded — leaving those endpoints cold, which
    is the opposite of what warmup is for.

    `verbose=True` prints per-endpoint timing.
    """
    if not client.check_connectivity():
        if verbose:
            print("  Aito unreachable — skipping cache warmup.")
        return

    def warm_or_skip(name: str, compute_fn) -> None:
        try:
            t0 = time.perf_counter()
            compute_fn()
            ms = int((time.perf_counter() - t0) * 1000)
            if verbose:
                print(f"  warm: {name:32s} ({ms} ms)")
        except Exception as exc:
            if verbose:
                print(f"  warm ERR {name}: {exc}")

    if verbose:
        print("Warming cache…")

    endpoints = [
        ("dashboard",        lambda: get_dashboard(client)),
        ("for-you maija",    lambda: get_for_you(client, persona_id="maija")),
        ("for-you olli",     lambda: get_for_you(client, persona_id="olli")),
        ("for-you saara",    lambda: get_for_you(client, persona_id="saara")),
        ("smart-search food (saara)",
         lambda: smart_search(client, query="food", persona_id="saara")),
        ("smart-search food (maija)",
         lambda: smart_search(client, query="food", persona_id="maija")),
        ("smart-search food (olli)",
         lambda: smart_search(client, query="food", persona_id="olli")),
        ("bought-together",    lambda: get_bought_together(client)),
        ("pattern-explorer",   lambda: get_patterns(client)),
        ("purchase-analytics", lambda: get_analytics(client)),
        ("product-filling",    lambda: get_filling(client)),
        ("feedback",           lambda: get_feedback(client)),
        ("price",              lambda: get_prices(client)),
        # Slow ones — each fans out ~20 parallel Aito calls
        # internally, so run them sequentially to stay under
        # Aito's per-instance inFlightWeight ceiling.
        ("churn",      lambda: get_churn(client)),
        ("demand",     lambda: get_demand(client)),
        ("inventory",  lambda: get_inventory(client)),
        ("evaluation", lambda: run_evaluation(client)),
    ]
    for name, fn in endpoints:
        warm_or_skip(name, fn)

    if verbose:
        print("Cache warm.")
