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
