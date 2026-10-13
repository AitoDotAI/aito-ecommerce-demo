"""A shopper's orders as of a month: everything the Shop's panels know
about their history (ADR 0031).

The grid, the drawer and the suggestions all read history through here,
so they agree on what "now" is: the month the user picked. An order in
that month or later hasn't happened yet.
"""

from __future__ import annotations

from src.aito_client import AitoClient, AitoError

MAX_ORDERS = 200


def orders_before(client: AitoClient, customer_id: str, month: str) -> list[dict]:
    """The customer's orders before `month`, oldest first."""
    res = client.search("orders", where={"customer_id": customer_id}, limit=MAX_ORDERS)
    if res["total"] > len(res["hits"]):
        raise AitoError(f"{customer_id} has {res['total']} orders, more than the {MAX_ORDERS} read")
    return sorted((o for o in res["hits"] if o["month"] < month), key=lambda o: o["month"])
