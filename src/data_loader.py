"""Upload the PetNord fixtures to Aito.

Usage:
    python -m src.data_loader              # create schemas + upload rows
    python -m src.data_loader --reset      # drop tables first, then load
    python -m src.data_loader --tables=products,customers   # subset

Wired into the `./do` script as `./do load-data` and `./do reset-data`.

The four tables (`products`, `customers`, `orders`, `order_lines`)
are loaded in **link-target order** — Aito rejects link writes whose
target row hasn't been created yet. Reset uses the reverse order.

This module is the table-of-contents for the Aito DB: an outside
reader who wants "what's actually in there" can read this file
top-to-bottom in two minutes. The `SCHEMAS` dict below is the
single source of truth; the cheatsheet (`docs/aito-cheatsheet.md`)
mirrors it as worked examples.

See `docs/adr/0003-aito-schema-and-loader.md` for the column-type
rationale — `String` vs `Text` vs `Decimal` — and the link-graph.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from src.aito_client import AitoClient, AitoError
from src.config import load_config
from src.schema import SCHEMAS


DATA_DIR = Path(__file__).resolve().parent.parent / "data"




BATCH_SIZE = 1000


# ── IO ──────────────────────────────────────────────────────────────


def load_fixture(table: str) -> list[dict]:
    path = DATA_DIR / f"{table}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Fixture file not found: {path}. "
            f"Run `./do generate-fixtures` first."
        )
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def create_schema(client: AitoClient, table: str, schema: dict) -> None:
    print(f"  Creating schema for '{table}'...")
    client._request("PUT", f"/schema/{table}", json=schema)


def upload_data(client: AitoClient, table: str, records: list[dict]) -> None:
    total = len(records)
    for i in range(0, total, BATCH_SIZE):
        batch = records[i:i + BATCH_SIZE]
        client._request("POST", f"/data/{table}/batch", json=batch)
        uploaded = min(i + BATCH_SIZE, total)
        print(f"  Uploaded {uploaded}/{total} rows to '{table}'")


def optimize_table(client: AitoClient, table: str) -> None:
    """Merge the table's batch segments into one, for faster reads.

    `upload_data` sends rows in ~1000-row batches, and each batch lands
    as its own segment — every read then has to touch all of them. On a
    125 k-row table (impressions) that's ~126 segments. Aito's
    `POST /data/{table}/optimize` rewrites the table as a single segment.
    Data-preserving and idempotent; the body is an empty object.
    """
    print(f"  Optimizing '{table}'...")
    client._request("POST", f"/data/{table}/optimize", json={})


def delete_table(client: AitoClient, table: str) -> None:
    print(f"  Deleting table '{table}'...")
    try:
        client._request("DELETE", f"/schema/{table}")
    except AitoError as exc:
        if exc.status_code == 404:
            print(f"  Table '{table}' does not exist, skipping.")
        else:
            raise


# ── Public API ─────────────────────────────────────────────────────


def run(*, reset: bool = False, tables: list[str] | None = None) -> None:
    """Bring up the PetNord DB.

    `tables` filters both delete and upload sets. Order is
    preserved from `SCHEMAS` (link-target first); for delete the
    order is reversed so linkers are dropped before their targets.
    """
    config = load_config()
    client = AitoClient(config)

    if not client.check_connectivity():
        print(f"Cannot connect to Aito at {config.aito_api_url}.")
        sys.exit(1)
    print(f"Connected to {config.aito_api_url}")

    selected = [t for t in SCHEMAS if (tables is None or t in tables)]
    if tables and not selected:
        print(f"No matching tables in {tables}. Known: {list(SCHEMAS)}.")
        sys.exit(2)

    if reset:
        print("Resetting — deleting existing tables...")
        # Reverse order: drop linkers before their targets so Aito
        # never complains about dangling links.
        delete_table(client, "prediction_cache")
        for table in reversed(selected):
            delete_table(client, table)

    print("Creating schemas...")
    for table in selected:
        create_schema(client, table, SCHEMAS[table])

    print("Uploading rows...")
    total = 0
    for table in selected:
        records = load_fixture(table)
        upload_data(client, table, records)
        total += len(records)

    # Batch uploads leave one segment per batch; merge them so reads
    # touch a single segment. See `optimize_table`.
    print("Optimizing (merge batch segments for faster reads)...")
    for table in selected:
        optimize_table(client, table)

    print(f"Done. Loaded {total} rows across {len(selected)} table(s).")


def optimize_all(tables: list[str] | None = None) -> None:
    """Optimize (segment-merge) all — or `tables` — without reloading.

    Backs `./do optimize`, and lets an already-loaded instance be
    optimized by hand without a full `reset-data`.
    """
    config = load_config()
    client = AitoClient(config)
    if not client.check_connectivity():
        print(f"Cannot connect to Aito at {config.aito_api_url}.")
        sys.exit(1)
    selected = [t for t in SCHEMAS if (tables is None or t in tables)]
    print(f"Optimizing {len(selected)} table(s) on {config.aito_api_url}")
    for table in selected:
        optimize_table(client, table)
    print("Done.")


def _parse_tables_arg(argv: list[str]) -> list[str] | None:
    for arg in argv:
        if arg.startswith("--tables="):
            value = arg.split("=", 1)[1].strip()
            return [t.strip() for t in value.split(",") if t.strip()]
    return None


if __name__ == "__main__":
    if "--optimize-only" in sys.argv:
        optimize_all(tables=_parse_tables_arg(sys.argv))
    else:
        reset = "--reset" in sys.argv
        tables = _parse_tables_arg(sys.argv)
        run(reset=reset, tables=tables)
