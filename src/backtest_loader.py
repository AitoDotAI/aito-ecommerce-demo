"""Load a prepared merchant dataset into its own Aito env, `backtest-<name>` (ADR 0036).

    AITO_ENV=backtest-<name> ./do backtest-load <name>

Loads only the training orders (`customers`, `invoices`, `lines`, ADR
0034's schema), so Aito never sees a test order. Writes only to the
dataset's own env and refuses any other, then checks each table's row
count on the server against what was sent.
"""

from __future__ import annotations

import json
import sys

from src.aito_client import AitoClient
from src.backtest_aito import aito_env_for
from src.backtest_prepared import dataset_dir
from src.config import load_config
from src.data_loader import create_schema, delete_table, optimize_table, upload_data
from src.uci_loader import require_env_exists
from src.uci_schema import UCI_SCHEMA

TABLES = ("customers", "invoices", "lines")   # link-target order


def run(name: str) -> None:
    config = load_config()
    env = aito_env_for(name)
    if config.aito_env != env:
        sys.exit(f"Refusing: AITO_ENV is {config.aito_env!r}; dataset {name!r} loads only into env {env!r}.")
    require_env_exists(config, env)
    directory = dataset_dir(name)
    rows = {}
    for table in TABLES:
        path = directory / f"{table}.json"
        if not path.exists():
            sys.exit(f"{path} is missing. Run `./do backtest-prepare shopify <export.csv> {name}` first.")
        rows[table] = json.loads(path.read_text(encoding="utf-8"))

    client = AitoClient(config)
    print(f"Loading {name} into {config.api_base}")
    for table in reversed(TABLES):
        delete_table(client, table)
    for table in TABLES:
        create_schema(client, table, UCI_SCHEMA[table])
        upload_data(client, table, rows[table])
        optimize_table(client, table)

    for table in TABLES:
        total = client.search(table, limit=0)["total"]
        print(f"  {table:10s} {total:>9,} (sent {len(rows[table]):,})")
        if total != len(rows[table]):
            sys.exit(f"Table {table}: the server holds {total} rows, {len(rows[table])} were sent.")
    print("Done.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python -m src.backtest_loader <name>")
    run(sys.argv[1])
