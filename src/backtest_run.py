"""Run the backtest of ADR 0036: rank, score, slice; Aito only when a client is given.

The three baselines are fitted on the training orders and asked for each
scored buyer's top 10. Aito, when run, answers the same buyers from its
env. Everything is scored against the buyer's first order on or after
the cutoff, which no method saw.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass

from src.aito_client import AitoClient
from src.backtest_aito import aito_rankings, explain_top_suggestion
from src.backtest_baselines import baselines
from src.backtest_dataset import BacktestDataset
from src.backtest_metrics import AITO, K, SliceResult, hit_at_1, slice_results

EXAMPLE_BUYERS = 10
# EASE inverts an item × item matrix: 20,000 items is ~3 GB of float64.
EASE_MAX_ITEMS = 20_000


@dataclass(frozen=True)
class ExampleBuyer:
    customer_id: str
    prior_orders: int
    top_code: str
    why: str
    ordered: list[str]         # the test order's codes, sorted
    hit: bool


@dataclass(frozen=True)
class BacktestRun:
    dataset: BacktestDataset
    slices: list[SliceResult]
    examples: list[ExampleBuyer]   # empty when Aito was not run
    aito_ran: bool


def baseline_rankings(dataset: BacktestDataset) -> dict[str, dict[str, list[str]]]:
    fit_ids, meta, basket, history = dataset.baseline_inputs()
    items = {code for order in dataset.train for code in order.codes}
    if len(items) > EASE_MAX_ITEMS:
        raise ValueError(f"{dataset.name}: {len(items):,} codes in training; EASE's item matrix "
                         f"over {EASE_MAX_ITEMS:,} codes would not fit in memory")
    rankings = {}
    for name, model in baselines().items():
        model.fit(fit_ids, meta, basket)
        rankings[name] = {c: model.recommend(c, history.get(c, []), K) for c in sorted(dataset.test_orders)}
    return rankings


def run_backtest(dataset: BacktestDataset, client: AitoClient | None = None,
                 progress: Callable[[int, int], None] | None = None) -> BacktestRun:
    rankings = baseline_rankings(dataset)
    customers = sorted(dataset.test_orders)
    prior = dataset.prior_orders()
    examples: list[ExampleBuyer] = []
    if client is not None:
        rankings[AITO] = aito_rankings(client, customers, progress)
        examples = [_example(client, dataset, c, prior[c], rankings[AITO][c]) for c in example_customers(customers)]
    test_codes = {c: order.codes for c, order in dataset.test_orders.items()}
    slices = slice_results(rankings, test_codes, prior)
    return BacktestRun(dataset, slices, examples, aito_ran=client is not None)


def example_customers(customers: list[str], count: int = EXAMPLE_BUYERS) -> list[str]:
    """Ten buyers picked by a hash of their id: fixed before any result,
    so the examples can't be chosen for how well Aito did on them."""
    return sorted(customers, key=lambda c: hashlib.sha256(c.encode("utf-8")).hexdigest())[:count]


def _example(client: AitoClient, dataset: BacktestDataset, customer: str, prior_orders: int,
             ranked: list[str]) -> ExampleBuyer:
    ordered = dataset.test_orders[customer].codes
    return ExampleBuyer(
        customer_id=customer,
        prior_orders=prior_orders,
        top_code=ranked[0],
        why=explain_top_suggestion(client, customer, ranked[0]),
        ordered=sorted(ordered),
        hit=bool(hit_at_1(ranked, ordered)),
    )

