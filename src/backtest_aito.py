"""The Aito method of the backtest: ADR 0034's `_predict`, one per scored buyer.

    {"from": "lines", "where": {"invoice.customer_id": id},
     "predict": "code", "limit": 10, "select": ["$p", "$value"]}

It is `src/uci_reorder_service.predicted_codes`, unchanged, so the ranking
measured here is the one the Business reorders page shows. A buyer new
after the cutoff has no lines in Aito; the same query then ranks codes
by their overall frequency, which is why the "0 prior orders" slice is
reported as a fallback when Aito equals popularity.

For the report's example buyers, a second `_predict` asks for the top
code's `$why` (the cheatsheet's `_predict` select with `{"$why": {}}`).
It is kept apart from the measured query so the measured body stays
byte-for-byte the benchmark's.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from src.aito_client import AitoClient, AitoError
from src.uci_reorder_service import predicted_codes
from src.why_processor import process_why

K = 10


def aito_env_for(dataset_name: str) -> str:
    """One env per dataset: `uci`, or `backtest-<name>` (ADR 0036)."""
    return "uci" if dataset_name == "uci" else f"backtest-{dataset_name}"


def require_dataset_env(client: AitoClient, dataset_name: str, aito_env: str) -> None:
    expected = aito_env_for(dataset_name)
    if aito_env != expected:
        raise SystemExit(f"Refusing: dataset {dataset_name!r} is loaded in env {expected!r}, "
                         f"and AITO_ENV is {aito_env!r}. Run with AITO_ENV={expected}.")
    if not client.use_v2:
        raise SystemExit("Refusing: the benchmarked query ran on API v2; unset AITO_USE_V2=0.")


def aito_rankings(client: AitoClient, customers: list[str],
                  progress: Callable[[int, int], None] | None = None) -> dict[str, list[str]]:
    rankings = {}
    for done, customer in enumerate(customers, start=1):
        rankings[customer] = [code for code, _ in predicted_codes(client, customer, K)]
        if progress:
            progress(done, len(customers))
    return rankings


def explain_top_suggestion(client: AitoClient, customer_id: str, top_code: str) -> str:
    """Aito's `$why` for the buyer's top code, as one line for the report."""
    response = client.predict_rows("lines", "code", where={"invoice.customer_id": customer_id},
                                   limit=1, select=["$p", "$value", {"$why": {}}])
    hits = response["hits"]
    if not hits or hits[0].get("$value") != top_code:
        raise AitoError(f"The $why query for customer {customer_id} ranked {hits[:1]} first, "
                        f"the measured query {top_code!r}: the two must agree")
    why = process_why(hits[0].get("$why"), top_code, actual_p=float(hits[0]["$p"]))
    if why is None:
        raise AitoError(f"_predict for customer {customer_id} returned no $why with a baseP: {hits[0]}")
    return why_line(why)


def why_line(why: dict, strongest: int = 3) -> str:
    """'base 1.2 %; ×8.4 when invoice.customer_id is 12357; ...', the
    strongest lifts (furthest from 1, either way) first."""
    for lift in why["lifts"]:
        if lift["lift"] <= 0:
            raise AitoError(f"A $why lift must be positive, got {lift}")
    lifts = sorted(why["lifts"], key=lambda lift: -abs(math.log(lift["lift"])))
    parts = [f"base {why['base_p']:.1%}"]
    for lift in lifts[:strongest]:
        conditions = " and ".join(
            f"{p['field']} {'is not' if p.get('negate') else 'is'} {p['value']}" for p in lift["propositions"])
        if not conditions:
            raise AitoError(f"A $why lift of {lift['lift']} came with no conditions: {lift}")
        parts.append(f"×{lift['lift']:.2f} when {conditions}")
    parts.append(f"p {why['final_p']:.1%}")
    return "; ".join(parts)
