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
from src.config import load_config
from src.data_loader import load_fixture

BATCH = 4000
COLUMNS = (
    ("orders", "previous_order", {"type": "String", "nullable": True, "link": "orders.order_id"}, "order_id"),
    ("orders", "basket_categories", {"type": "Text", "nullable": True, "analyzer": "whitespace"}, "order_id"),
    ("contexts", "last_order", {"type": "String", "nullable": True, "link": "orders.order_id"}, "context_id"),
)


def main() -> int:
    cfg = load_config()
    client = AitoClient(cfg)
    rows = {"orders": load_fixture("orders"), "contexts": load_fixture("contexts")}
    for table in rows:
        live = client.search(table, limit=0)["total"]
        assert live == len(rows[table]), f"{cfg.aito_env} holds {live} {table}, the fixture {len(rows[table])}"
    have = {t: set(client._request("GET", f"/schema/{t}")["columns"]) for t in rows}
    todo = [c for c in COLUMNS if c[1] not in have[c[0]]]
    print(f"env {cfg.aito_env}: columns to add: {[f'{t}.{c}' for t, c, _, _ in todo] or 'none, already there'}")
    if not apply_requested():
        print("Dry run: nothing written. Re-run with --apply.")
        return 0
    for table, column, spec, key in todo:
        client._request("PUT", f"/schema/{table}/{column}", json=spec)
        with_value = [r for r in rows[table] if column in r]
        for i in range(0, len(with_value), BATCH):
            chunk = with_value[i:i + BATCH]
            client._request("POST", f"/data/{table}/_backfill", json={
                "key": key, "keys": [r[key] for r in chunk], "columns": {column: [r[column] for r in chunk]}})
        print(f"added {table}.{column}: {len(with_value)} rows carry a value")
    for table in rows:
        client._request("POST", f"/data/{table}/optimize", json={})
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
