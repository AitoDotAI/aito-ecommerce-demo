"""The train/test split of a merchant's orders (ADR 0036), fixed before any metric.

- The cutoff is the first day of the month that holds the order at the
  75th percentile of order dates. It is computed from the dates alone.
- Train = the orders before the cutoff; only they are loaded into Aito.
- Test = each buyer's first order on or after it, as the benchmark's
  `retail2_run.targets()`: on a tied date the lowest order id wins.

UCI keeps the benchmark's own cutoff, 2011-09-01 (`src/uci_tables.py`).
"""

from __future__ import annotations

import math

from src.backtest_dataset import BacktestDataset, HeldOutOrder, TrainOrder
from src.uci_tables import Invoice

CUTOFF_PERCENTILE = 0.75


def cutoff_date(order_dates: list[str]) -> str:
    """The first day of the month of the 75th-percentile order date.

    The percentile is the nearest rank: the date at position
    ceil(0.75 · n) in the sorted dates, counting from 1.
    """
    if not order_dates:
        raise ValueError("No orders: a cutoff needs at least one order date")
    dates = sorted(order_dates)
    at_percentile = dates[math.ceil(CUTOFF_PERCENTILE * len(dates)) - 1]
    return f"{at_percentile[:7]}-01"


def split_orders(name: str, source: str, invoices: dict[str, Invoice], cutoff: str,
                 dropped_rows: dict[str, int], notes: dict[str, int]) -> BacktestDataset:
    train = [
        TrainOrder(i, invoices[i].customer_id, invoices[i].date[:7], tuple(sorted(invoices[i].codes)))
        for i in sorted(invoices) if invoices[i].date < cutoff
    ]
    first: dict[str, Invoice] = {}
    for invoice_id in sorted(invoices):
        invoice = invoices[invoice_id]
        if invoice.date < cutoff:
            continue
        if invoice.customer_id not in first or invoice.date < first[invoice.customer_id].date:
            first[invoice.customer_id] = invoice
    test_orders = {customer: HeldOutOrder(inv.invoice, inv.date, inv.codes) for customer, inv in first.items()}
    if not train:
        raise ValueError(f"{name}: no order before the cutoff {cutoff}, nothing to train on")
    return BacktestDataset(name, source, cutoff, train, test_orders, dropped_rows, notes)
