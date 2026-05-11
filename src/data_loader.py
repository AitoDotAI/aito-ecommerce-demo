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


DATA_DIR = Path(__file__).resolve().parent.parent / "data"


# ── Schemas — keep in lock-step with `docs/aito-cheatsheet.md` ─────
#
# Load order: dict insertion order is the load order. Don't reorder
# without checking the link graph: linkers come after their targets.

SCHEMAS: dict[str, dict] = {
    # 1. products — link target for order_lines.product_sku.
    "products": {
        "type": "table",
        "columns": {
            "sku":       {"type": "String",  "nullable": False},
            # Text so `_search { name: "food" }` tokenises on
            # individual words. Critical for the Smart Search rank-
            # flip moment.
            "name":      {"type": "Text",    "nullable": False},
            "category":  {"type": "String",  "nullable": False},
            "pet_type":  {"type": "String",  "nullable": False},
            "brand":     {"type": "String",  "nullable": False},
            "price_eur": {"type": "Decimal", "nullable": False},
            # Nullable triple — drives the Product Filling demo's
            # input pile. ~5 % of products have ≥ 2 of these nulled.
            "weight_kg": {"type": "Decimal", "nullable": True},
            "dietary":   {"type": "String",  "nullable": True},
            "tax_class": {"type": "String",  "nullable": True},
        },
    },
    # 2. customers — link target for orders.customer_id.
    "customers": {
        "type": "table",
        "columns": {
            "customer_id":   {"type": "String", "nullable": False},
            "segment":       {"type": "String", "nullable": False},
            # `pet_size` is set only for dog_owner / multi_pet rows;
            # nullable so the segments that don't have one don't
            # have to invent a placeholder.
            "pet_size":      {"type": "String", "nullable": True},
            "region":        {"type": "String", "nullable": False},
            "tenure_months": {"type": "Int",    "nullable": False},
        },
    },
    # 3. orders — links to customers.
    "orders": {
        "type": "table",
        "columns": {
            "order_id":    {"type": "String",  "nullable": False},
            "customer_id": {"type": "String",  "nullable": False,
                            "link": "customers.customer_id"},
            # String (not Date) so `_relate` treats months
            # categorically — that's what surfaces seasonality
            # patterns directly in the Pattern Explorer view.
            "month":       {"type": "String",  "nullable": False},
            "total_eur":   {"type": "Decimal", "nullable": False},
        },
    },
    # 4. order_lines — links to orders AND products. Load last.
    "order_lines": {
        "type": "table",
        "columns": {
            "line_id":     {"type": "String",  "nullable": False},
            "order_id":    {"type": "String",  "nullable": False,
                            "link": "orders.order_id"},
            "product_sku": {"type": "String",  "nullable": False,
                            "link": "products.sku"},
            "qty":         {"type": "Int",     "nullable": False},
            "returned":    {"type": "Boolean", "nullable": False},
            # Denormalised mirror of `customers.{segment, pet_size}`.
            # Aito's queries from `order_lines` only do single-hop
            # link traversal — to bias by customer attributes without
            # a two-hop chain (`order_id → orders → customer_id →
            # customers`) we pull the demo-load-bearing customer
            # fields down to the line level. Drives Smart Search's
            # customer-context biasing. See ADR 0006.
            "customer_segment":  {"type": "String", "nullable": False},
            "customer_pet_size": {"type": "String", "nullable": True},
        },
    },
}


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

    print(f"Done. Loaded {total} rows across {len(selected)} table(s).")


def _parse_tables_arg(argv: list[str]) -> list[str] | None:
    for arg in argv:
        if arg.startswith("--tables="):
            value = arg.split("=", 1)[1].strip()
            return [t.strip() for t in value.split(",") if t.strip()]
    return None


if __name__ == "__main__":
    reset = "--reset" in sys.argv
    tables = _parse_tables_arg(sys.argv)
    run(reset=reset, tables=tables)
