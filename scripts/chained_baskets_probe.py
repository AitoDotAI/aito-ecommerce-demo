#!/usr/bin/env python3
"""ADR 0047's probes, on a throwaway branch of release2: add the chained-basket columns in place, then ask.

    PYTHONPATH=. AITO_ENV=release2 python scripts/chained_baskets_probe.py [--apply]

Default is a dry run (reads, writes nothing). With --apply it makes one branch of env release2, adds
`orders.previous_order`, `orders.basket_categories` and `contexts.last_order` there (v2's in-place
`PUT /schema` + `_backfill`, never a drop and reload), runs the probes the ADR lists, and deletes the
branch. release2 and master are never written.
"""
from __future__ import annotations

import dataclasses
import json
import sys
import time

import httpx

from src.aito_client import AitoClient
from src.config import load_config
from src.data_loader import load_fixture

BRANCH = "chain-probe"
SOURCE = "release2"
BATCH = 4000
apply = "--apply" in sys.argv


def main() -> int:
    cfg = load_config()
    base = cfg.aito_api_url
    http = httpx.Client(headers={"x-api-key": cfg.aito_api_key, "content-type": "application/json"}, timeout=300)

    def call(method: str, path: str, **kw) -> dict:
        r = http.request(method, path if path.startswith("http") else f"{base}{path}", **kw)
        if r.status_code >= 400:
            raise RuntimeError(f"{method} {path} answered {r.status_code}: {r.text[:500]}")
        return r.json() if r.content else {}

    orders, contexts = load_fixture("orders"), load_fixture("contexts")
    linked_orders = [o for o in orders if "previous_order" in o]
    linked_contexts = [c for c in contexts if "last_order" in c]
    print(f"orders {len(orders)} ({len(linked_orders)} with previous_order); contexts {len(contexts)} "
          f"({len(linked_contexts)} with last_order)")
    live = call("POST", f"/env/{SOURCE}/api/v2/_search", json={"from": "orders", "limit": 0})
    total = (live.get("data") or live)["total"]
    assert total == len(orders), f"{SOURCE} holds {total} orders, the fixture {len(orders)}"
    if not apply:
        print("Dry run: nothing written. Re-run with --apply.")
        return 0

    env = lambda path: f"/env/{BRANCH}/api/v2{path}"
    try:
        call("POST", "/api/v1/_envs", json={"name": BRANCH, "basedOn": f"env.{SOURCE}"})
        print("1. branch made")
        for table, column, spec in (
                ("orders", "previous_order", {"type": "String", "nullable": True, "link": "orders.order_id"}),
                ("orders", "basket_categories", {"type": "Text", "nullable": True, "analyzer": "whitespace"}),
                ("contexts", "last_order", {"type": "String", "nullable": True, "link": "orders.order_id"})):
            print(f"2. add {table}.{column}:", call("PUT", env(f"/schema/{table}/{column}"), json=spec))
        for table, key, rows, column in (("orders", "order_id", linked_orders, "previous_order"),
                                         ("orders", "order_id", orders, "basket_categories"),
                                         ("contexts", "context_id", linked_contexts, "last_order")):
            for i in range(0, len(rows), BATCH):
                chunk = rows[i:i + BATCH]
                call("POST", env(f"/data/{table}/_backfill"),
                     json={"key": key, "keys": [r[key] for r in chunk], "columns": {column: [r[column] for r in chunk]}})
            print(f"3. backfilled {table}.{column}: {len(rows)} rows")
        for table in ("orders", "contexts"):
            call("POST", env(f"/data/{table}/optimize"), json={})
        print("4. optimized")

        client = AitoClient(dataclasses.replace(cfg, aito_env=BRANCH))
        by_id = {o["order_id"]: o for o in load_fixture("orders")}
        # A session whose last order itself has a predecessor, so the second hop has something to read.
        sample = next(c for c in linked_contexts if "previous_order" in by_id[c["last_order"]])
        last = by_id[sample["last_order"]]
        words = last["basket_categories"].split()
        base_where = {"context.month": sample["month"], "just_bought": False}
        one_hop = {"$and": [{"$match": w} for w in words]}
        probes = {
            "P1 one hop": {**base_where, "context.last_order.basket_categories": one_hop},
            "P1b same words as cart words": {**base_where, "context.basket_categories": one_hop},
        }
        if "previous_order" in last:
            probes["P2 two hops"] = {**base_where, "context.last_order.previous_order.basket_categories":
                                     {"$and": [{"$match": w} for w in by_id[last["previous_order"]]["basket_categories"].split()]}}
        for name, where in probes.items():
            try:
                started = time.perf_counter()
                hits = client.recommend("impressions", where, "product_sku", {"purchased": True},
                                        select=["sku", "name", "$p", "$why"], limit=5)["hits"]
                print(f"5. {name}: top {[(h['name'][:24], round(h['$p'], 2)) for h in hits[:3]]} in {time.perf_counter() - started:.2f} s")
                if name == "P1 one hop":
                    props = []
                    def walk(n):
                        for f in n.get("factors", []) or []:
                            if f["type"] == "relatedPropositionLift":
                                props.append((json.dumps(f["proposition"])[:90], round(f["value"], 2)))
                            walk(f)
                    walk(hits[0]["$why"])
                    print("   $why propositions of the top hit:", props)
            except Exception as exc:    # noqa: BLE001: a probe's failure is the finding
                print(f"5. {name}: FAILED {str(exc)[:400]}")
        # A context without a link must not count for a path condition.
        counted = client.search("impressions", where={"context.last_order.basket_categories": {"$match": words[0]}}, limit=0)["total"]
        print(f"6. impressions whose last order holds {words[0]!r}: {counted} (total impressions on the branch: "
              f"{client.search('impressions', limit=0)['total']})")
    finally:
        http.delete(f"{base}/api/v1/_envs/{BRANCH}")
        print("7. branch deleted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
