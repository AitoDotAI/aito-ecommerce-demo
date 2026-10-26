"""Chained baskets (ADR 0047): each order points to the one before it, each session to the last order
before its month.

Derived at load time from the orders the fixtures already hold, so the seeded fixtures stay as they are.
An order's `previous_order` is its customer's order just before it, by (month, order_id); a context's
`last_order` is the customer's latest order of an **earlier month**, so a session never links to an order
of its own month or later. A missing link is an absent key, as Aito leaves a null out.
"""

from __future__ import annotations

from collections import defaultdict

from src.shop_context import basket_words


def link_orders(orders: list[dict], products: dict[str, dict]) -> list[dict]:
    """The orders with `previous_order` (a link to the customer's order before) and `basket_categories`."""
    previous: dict[str, str] = {}
    by_customer: dict[str, list[dict]] = defaultdict(list)
    for order in orders:
        by_customer[order["customer_id"]].append(order)
    for chain in by_customer.values():
        chain.sort(key=lambda o: (o["month"], o["order_id"]))
        for before, after in zip(chain, chain[1:]):
            previous[after["order_id"]] = before["order_id"]
    linked = []
    for order in orders:
        row = {**order, "basket_categories": " ".join(basket_words([products[s] for s in sorted(set(order["skus"].split()))]))}
        if order["order_id"] in previous:
            row["previous_order"] = previous[order["order_id"]]
        linked.append(row)
    return linked


def link_contexts(contexts: list[dict], orders: list[dict]) -> list[dict]:
    """The contexts with `last_order`: the customer's latest order in a month before the context's."""
    by_customer: dict[str, list[dict]] = defaultdict(list)
    for order in orders:
        by_customer[order["customer_id"]].append(order)
    for chain in by_customer.values():
        chain.sort(key=lambda o: (o["month"], o["order_id"]))
    linked = []
    for context in contexts:
        earlier = [o for o in by_customer.get(context.get("customer"), []) if o["month"] < context["month"]]
        linked.append({**context, "last_order": earlier[-1]["order_id"]} if earlier else context)
    return linked


# ── Adding the columns to an env loaded before ADR 0047 ──────────────────────────────────────────
#
# v2's in-place schema evolution (`PUT /schema` + `_backfill`, never a drop and reload, which would land
# the table on the v1 engine), verified on a throwaway branch of release2 on 2026-10-25.

BATCH = 4000
COLUMNS = (
    ("orders", "previous_order", {"type": "String", "nullable": True, "link": "orders.order_id"}, "order_id"),
    ("orders", "basket_categories", {"type": "Text", "nullable": True, "analyzer": "whitespace"}, "order_id"),
    ("contexts", "last_order", {"type": "String", "nullable": True, "link": "orders.order_id"}, "context_id"),
)


def missing_columns(client, tables=("orders", "contexts")) -> list[tuple]:
    have = {t: set(client._request("GET", f"/schema/{t}")["columns"]) for t in tables}
    return [c for c in COLUMNS if c[1] not in have[c[0]]]


def add_columns(client, rows: dict[str, list[dict]], todo: list[tuple] | None = None) -> None:
    """Add the columns an env lacks and backfill them from `rows` ({"orders": linked, "contexts": linked})."""
    for table, column, spec, key in missing_columns(client) if todo is None else todo:
        client._request("PUT", f"/schema/{table}/{column}", json=spec)
        with_value = [r for r in rows[table] if column in r]
        for i in range(0, len(with_value), BATCH):
            chunk = with_value[i:i + BATCH]
            client._request("POST", f"/data/{table}/_backfill", json={
                "key": key, "keys": [r[key] for r in chunk], "columns": {column: [r[column] for r in chunk]}})
    for table in rows:
        client._request("POST", f"/data/{table}/optimize", json={})
