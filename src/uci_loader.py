"""Load the prepared UCI data into Aito env `uci`.

    AITO_ENV=uci ./do uci-load

Drops and recreates the five UCI tables (`src/uci_schema.py`) from
`data/uci/*.json` (written by `./do uci-prepare`), then checks each
table's row count on the server against what was sent. A load that lost
rows would quietly measure a different model, so a mismatch fails.

Writes only to env `uci`, and refuses any other: the pet shop's
`customers` table shares a name with UCI's, and loading into its env
would replace it.
"""

from __future__ import annotations

import json
import sys

import httpx

from src.aito_client import AitoClient
from src.config import Config, load_config
from src.data_loader import create_schema, delete_table, optimize_table, upload_data
from src.uci_outcomes import UCI_DATA_DIR
from src.uci_schema import UCI_SCHEMA
from src.uci_tables import EXPECTED_COUNTS

UCI_ENV = "uci"


def run() -> None:
    config = load_config()
    if config.aito_env != UCI_ENV:
        sys.exit(f"Refusing: AITO_ENV is {config.aito_env!r}; the UCI loader writes only to env {UCI_ENV!r}.")
    _require_env_exists(config)
    rows = {table: _prepared_rows(table) for table in UCI_SCHEMA}
    _check_expected_counts(rows)

    client = AitoClient(config)
    print(f"Loading UCI Online Retail II into {config.api_base}")
    for table in reversed(UCI_SCHEMA):      # linkers before their targets
        delete_table(client, table)
    for table, schema in UCI_SCHEMA.items():
        create_schema(client, table, schema)
        upload_data(client, table, rows[table])
        optimize_table(client, table)

    print("Row counts on the server:")
    for table in UCI_SCHEMA:
        total = client.search(table, limit=0)["total"]
        print(f"  {table:10s} {total:>9,} (sent {len(rows[table]):,})")
        if total != len(rows[table]):
            sys.exit(f"Table {table}: the server holds {total} rows, {len(rows[table])} were sent.")
    print("Done.")


def _require_env_exists(config: Config) -> None:
    """Fail before writing if the env isn't there; we don't create one here."""
    response = httpx.get(f"{config.aito_api_url}/api/v1/_envs",
                         headers={"x-api-key": config.aito_api_key}, timeout=30.0)
    response.raise_for_status()
    names = {env.get("name") for env in response.json().get("envs", [])}
    if UCI_ENV not in names:
        sys.exit(f"Env {UCI_ENV!r} does not exist on {config.aito_api_url} (envs: {sorted(names)}). "
                 f"Create it first; this loader only fills it.")


def _prepared_rows(table: str) -> list[dict]:
    path = UCI_DATA_DIR / f"{table}.json"
    if not path.exists():
        sys.exit(f"{path} is missing. Run `./do uci-prepare` first.")
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _check_expected_counts(rows: dict[str, list[dict]]) -> None:
    """The benchmark's training data: refuse to load anything else."""
    for table, expected_key in (("invoices", "train invoices"), ("lines", "lines")):
        if len(rows[table]) != EXPECTED_COUNTS[expected_key]:
            sys.exit(f"data/uci/{table}.json has {len(rows[table]):,} rows, "
                     f"the benchmark loaded {EXPECTED_COUNTS[expected_key]:,}.")


if __name__ == "__main__":
    run()
