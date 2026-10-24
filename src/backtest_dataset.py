"""One backtest dataset, whatever its source (ADR 0036).

Every adapter (UCI, a Shopify export) ends here: the training orders, the
order each scored buyer placed first on or after the cutoff, and what the
adapter dropped on the way. The methods and the metrics read only this.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field


@dataclass(frozen=True)
class TrainOrder:
    order_id: str
    customer_id: str
    month: str                 # "YYYY-MM": the only time the baselines and Aito see
    codes: tuple[str, ...]     # a set of codes, sorted, so every run iterates them alike


@dataclass(frozen=True)
class HeldOutOrder:
    order_id: str
    date: str                  # "YYYY-MM-DD"
    codes: frozenset[str]


@dataclass(frozen=True)
class BacktestDataset:
    name: str                  # "uci", or the name a Shopify export was prepared under
    source: str                # one line for the report's header
    cutoff: str                # "YYYY-MM-DD": train before, test on and after
    train: list[TrainOrder]    # sorted by order id
    test_orders: dict[str, HeldOutOrder]          # per scored buyer
    dropped_rows: dict[str, int] = field(default_factory=dict)
    notes: dict[str, int] = field(default_factory=dict)   # counted, not dropped

    def __post_init__(self) -> None:
        ids = [order.order_id for order in self.train]
        if ids != sorted(set(ids)):
            raise ValueError(f"{self.name}: training order ids must be unique and sorted")
        if not self.test_orders:
            raise ValueError(f"{self.name}: no buyer has an order on or after {self.cutoff}")

    def prior_orders(self) -> dict[str, int]:
        """Training orders per scored buyer, 0 for a buyer new after the cutoff."""
        counts = Counter(order.customer_id for order in self.train)
        return {customer: counts[customer] for customer in self.test_orders}

    def baseline_inputs(self) -> tuple[list[str], dict, dict, dict[str, list]]:
        """`fit_ids`, `meta`, `basket` and per-buyer `history`, in the shapes
        the benchmark's baselines take (`src/backtest_baselines.py`)."""
        fit_ids = [order.order_id for order in self.train]
        meta = {order.order_id: (order.customer_id, order.month) for order in self.train}
        basket = {order.order_id: order.codes for order in self.train}
        history: dict[str, list] = defaultdict(list)
        for order in self.train:          # sorted by id, so a month's orders stay in id order
            history[order.customer_id].append((order.month, order.codes, order.order_id))
        for orders in history.values():
            orders.sort(key=lambda entry: entry[0])
        return fit_ids, meta, basket, history
