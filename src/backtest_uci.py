"""The UCI Online Retail II backtest dataset, from ADR 0034's prepared files.

`./do uci-prepare` writes `data/uci/`: the training tables loaded into
env `uci` (`invoices.json`, `lines.json`), each loaded buyer's next order
(`outcomes.json`) and the next order of each buyer new after the cutoff
(`new_buyers.json`). Those are the benchmark's data exactly
(`EXPECTED_COUNTS`), so nothing is re-derived from the raw file here.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from src.backtest_dataset import BacktestDataset, HeldOutOrder, TrainOrder
from src.uci_outcomes import UCI_DATA_DIR
from src.uci_tables import EXPECTED_COUNTS, TRAIN_BEFORE

SOURCE = ("UCI Online Retail II (Chen, 2012, https://doi.org/10.24432/C5CG6D, CC BY 4.0), "
          "prepared as Aito core's benchmark did (ADR 0034)")


def load_uci_dataset(data_dir: Path = UCI_DATA_DIR) -> BacktestDataset:
    invoices = _read(data_dir, "invoices")
    lines = _read(data_dir, "lines")
    codes: dict[str, set[str]] = defaultdict(set)
    for line in lines:
        codes[line["invoice"]].add(line["code"])
    train = [TrainOrder(row["invoice"], row["customer_id"], row["month"], tuple(sorted(codes[row["invoice"]])))
             for row in sorted(invoices, key=lambda row: row["invoice"])]

    test_orders = {customer: _test_order(row["next_order"])
                   for customer, row in _read(data_dir, "outcomes").items() if row["next_order"]}
    new_buyers = _read(data_dir, "new_buyers")
    returning = test_orders.keys() & new_buyers.keys()
    if returning:
        raise ValueError(f"{sorted(returning)[:5]} are in both outcomes.json and new_buyers.json")
    test_orders.update({customer: _test_order(order) for customer, order in new_buyers.items()})

    dataset = BacktestDataset("uci", SOURCE, TRAIN_BEFORE, train, test_orders)
    _check_benchmark_counts(dataset, len(lines))
    return dataset


def _check_benchmark_counts(dataset: BacktestDataset, line_count: int) -> None:
    prior = dataset.prior_orders()
    counts = {
        "train invoices": len(dataset.train),
        "lines": line_count,
        "scored customers": len(dataset.test_orders),
        "scored with 1-2 prior invoices": sum(1 for n in prior.values() if 1 <= n <= 2),
        "scored with 0 prior invoices": sum(1 for n in prior.values() if n == 0),
    }
    expected = {name: EXPECTED_COUNTS[name] for name in counts}
    if counts != expected:
        raise ValueError(f"data/uci/ is not the benchmark's data: {counts}, expected {expected}. "
                         f"Re-run `./do uci-prepare`.")


def _test_order(row: dict) -> HeldOutOrder:
    return HeldOutOrder(row["invoice"], row["date"], frozenset(row["codes"]))


def _read(data_dir: Path, name: str):
    path = data_dir / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing. Run `./do uci-prepare` (reads the UCI xlsx).")
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)
