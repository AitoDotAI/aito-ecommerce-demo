"""A merchant's export, prepared once into `data/backtest/<name>/` (ADR 0036).

    ./do backtest-prepare shopify <orders_export.csv> <name>

writes, before any metric exists:
- `split.json`: the cutoff, the export's md5, the dropped-row counts.
  It pins the split: preparing again with another file or another cutoff
  refuses, so a run can't be repeated until a split looks good.
- `customers.json`, `invoices.json`, `lines.json`: the training orders in
  ADR 0034's table shapes, for `./do backtest-load` into env backtest-<name>;
- `test_orders.json`: each scored buyer's first order on or after the cutoff.

`data/backtest/` is gitignored: a merchant's data never enters the repo.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

from src.backtest_dataset import BacktestDataset, HeldOutOrder, TrainOrder
from src.backtest_shopify import read_shopify_export
from src.backtest_split import cutoff_date, split_orders
from src.uci_tables import aito_rows

BACKTEST_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "backtest"
NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,30}$")


def dataset_dir(name: str, root: Path = BACKTEST_DATA_DIR) -> Path:
    if name == "uci" or not NAME_PATTERN.match(name):
        raise ValueError(f"Dataset name {name!r}: use lower-case letters, digits and '-' "
                         f"(it names the Aito env backtest-{name}); 'uci' is taken")
    return root / name


def prepare_shopify(export: Path, name: str, root: Path = BACKTEST_DATA_DIR) -> BacktestDataset:
    directory = dataset_dir(name, root)
    orders = read_shopify_export(export)
    cutoff = cutoff_date([invoice.date for invoice in orders.invoices.values()])
    split = {"name": name, "source": f"Shopify orders export {export.name}",
             "export_md5": hashlib.md5(export.read_bytes()).hexdigest(), "cutoff": cutoff,
             "dropped_rows": dict(sorted(orders.dropped_rows.items())), "notes": dict(sorted(orders.notes.items()))}
    _refuse_a_different_split(directory, split)

    dataset = split_orders(name, split["source"], orders.invoices, cutoff,
                           split["dropped_rows"], split["notes"])
    train_ids = [order.order_id for order in dataset.train]
    tables = aito_rows(orders.invoices, train_ids)
    test_orders = {customer: {"invoice": order.order_id, "date": order.date, "codes": sorted(order.codes)}
                   for customer, order in sorted(dataset.test_orders.items())}

    directory.mkdir(parents=True, exist_ok=True)
    for file_name, content in {**tables, "test_orders": test_orders, "split": split}.items():
        with (directory / f"{file_name}.json").open("w", encoding="utf-8") as fh:
            json.dump(content, fh, indent=1 if file_name == "split" else None)
    return dataset


def load_prepared(name: str, root: Path = BACKTEST_DATA_DIR) -> BacktestDataset:
    directory = dataset_dir(name, root)
    if not (directory / "split.json").exists():
        raise FileNotFoundError(f"{directory} holds no prepared dataset. "
                                f"Run `./do backtest-prepare shopify <export.csv> {name}` first.")
    split, invoices, lines, test_orders = (
        json.loads((directory / f"{file_name}.json").read_text(encoding="utf-8"))
        for file_name in ("split", "invoices", "lines", "test_orders"))
    codes: dict[str, set[str]] = defaultdict(set)
    for line in lines:
        codes[line["invoice"]].add(line["code"])
    train = [TrainOrder(row["invoice"], row["customer_id"], row["month"], tuple(sorted(codes[row["invoice"]])))
             for row in sorted(invoices, key=lambda row: row["invoice"])]
    tests = {customer: HeldOutOrder(row["invoice"], row["date"], frozenset(row["codes"]))
             for customer, row in test_orders.items()}
    return BacktestDataset(name, split["source"], split["cutoff"], train, tests,
                           split["dropped_rows"], split["notes"])


def _refuse_a_different_split(directory: Path, split: dict) -> None:
    path = directory / "split.json"
    if not path.exists():
        return
    pinned = json.loads(path.read_text(encoding="utf-8"))
    for key in ("export_md5", "cutoff"):
        if pinned[key] != split[key]:
            raise SystemExit(f"Refusing: {path} pins {key} {pinned[key]!r}, this run gives {split[key]!r}. "
                             f"A dataset's split is fixed once; prepare a new name for a new export.")
