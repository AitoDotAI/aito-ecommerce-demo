#!/usr/bin/env python3
"""Add ADR 0047's chained-basket columns to an existing env, in place.

    PYTHONPATH=. AITO_ENV=<env> python scripts/add_chained_baskets.py [--apply]

For an env loaded before ADR 0047: `orders.previous_order`, `orders.basket_categories` and
`contexts.last_order`, by v2's in-place `PUT /schema` + `_backfill` (never a drop and reload, which would
land the table on the v1 engine). Values are the loader's own (`src/chained_baskets.py`), so a fresh load
and this migration agree. Default is a dry run: it checks the env holds the fixtures' rows and writes
nothing. Verified on a throwaway branch first (`scripts/chained_baskets_probe.py`, 2026-10-25).
"""
from __future__ import annotations

import sys

from src.aito_client import AitoClient
from src.chained_baskets import COLUMNS, add_columns, missing_columns
from src.config import load_config
from src.data_loader import load_fixture


def main() -> int:
    cfg = load_config()
    client = AitoClient(cfg)
    rows = {"orders": load_fixture("orders"), "contexts": load_fixture("contexts")}
    for table in rows:
        live = client.search(table, limit=0)["total"]
        assert live == len(rows[table]), f"{cfg.aito_env} holds {live} {table}, the fixture {len(rows[table])}"
    todo = missing_columns(client)
    print(f"env {cfg.aito_env}: columns to add: {[f'{t}.{c}' for t, c, _, _ in todo] or 'none, already there'}")
    if not apply_requested():
        print("Dry run: nothing written. Re-run with --apply.")
        return 0
    add_columns(client, rows, todo)
    print(f"added: {[f'{t}.{c}' for t, c, _, _ in todo] or 'nothing'}")
    # Verify: every row's value reads back as the loader derives it.
    for table, column, _, key in COLUMNS:
        want = {r[key]: r[column] for r in rows[table] if column in r}
        got = {}
        for offset in range(0, len(rows[table]), 5000):
            for h in client.search(table, select=[key, column], where={column: {"$exists": True}}, limit=5000, offset=offset)["hits"]:
                got[h[key]] = h[column]
        assert got == want, f"{table}.{column}: {len(set(want) ^ set(got))} rows differ after the backfill"
        print(f"verified {table}.{column}: {len(got)} values read back equal the loader's")
    return 0


def apply_requested() -> bool:
    return "--apply" in sys.argv


if __name__ == "__main__":
    sys.exit(main())
