"""Backtest the reorder suggestion on a merchant's orders (ADR 0036).

    ./do backtest-prepare shopify <orders_export.csv> <name>   # once; pins the cutoff
    AITO_ENV=backtest-<name> ./do backtest-load <name>          # training orders → Aito
    ./do backtest <name> [--offline]
    ./do backtest uci [--offline]                               # needs ./do uci-prepare

`--offline` runs the three baselines only, with no Aito call. Otherwise
AITO_ENV must name the dataset's env (`uci`, or `backtest-<name>`).
The report is written to `data/backtest/<name>/report.md` (gitignored).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.aito_client import AitoClient
from src.backtest_aito import require_dataset_env
from src.backtest_dataset import BacktestDataset
from src.backtest_prepared import BACKTEST_DATA_DIR, load_prepared, prepare_shopify
from src.backtest_report import render_report
from src.backtest_run import run_backtest
from src.backtest_uci import load_uci_dataset
from src.config import load_config


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="./do backtest", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="a Shopify orders export → data/backtest/<name>/")
    prepare.add_argument("source", choices=["shopify"])
    prepare.add_argument("export", type=Path)
    prepare.add_argument("name")
    run = commands.add_parser("run", help="score the methods, write the report")
    run.add_argument("dataset", help="'uci', or a prepared dataset's name")
    run.add_argument("--offline", action="store_true", help="baselines only, no Aito call")
    args = parser.parse_args(argv)

    if args.command == "prepare":
        dataset = prepare_shopify(args.export, args.name)
        print(f"Prepared {args.name}: cutoff {dataset.cutoff}, {len(dataset.train):,} training orders, "
              f"{len(dataset.test_orders):,} scored buyers")
        print(f"  dropped rows: {dataset.dropped_rows or 'none'}; counted: {dataset.notes or 'none'}")
        return
    _run(args.dataset, offline=args.offline)


def _run(name: str, offline: bool) -> None:
    dataset: BacktestDataset = load_uci_dataset() if name == "uci" else load_prepared(name)
    client = None
    if not offline:
        config = load_config()
        client = AitoClient(config)
        require_dataset_env(client, name, config.aito_env)
        print(f"Aito: {config.api_base}")
    print(f"{name}: cutoff {dataset.cutoff}, {len(dataset.test_orders):,} scored buyers")
    result = run_backtest(dataset, client, progress=_progress)
    report = render_report(result)
    path = BACKTEST_DATA_DIR / name / "report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
    print(report)
    print(f"Wrote {path}")


def _progress(done: int, total: int) -> None:
    if done % 250 == 0 or done == total:
        print(f"  Aito {done:,}/{total:,}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
