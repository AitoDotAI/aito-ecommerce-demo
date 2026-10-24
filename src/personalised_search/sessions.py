"""The scored sessions of the personalised-search benchmark (ADR 0037 §3).

A scored session is a generated search session in which the shopper
bought something, except the three hand-curated personas. A hit is any
product bought in that session. Everything here is read from the
committed fixtures (and the regenerated, gitignored `impressions.json`),
so the set is fixed before Aito is asked anything.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from data.generate_fixtures import PERSONAS

DATA = Path(__file__).resolve().parents[2] / "data"
# The shopper's orders before the session's month, as ADR 0037's slices.
SLICES = ("0", "1-2", "3-5", "6+")


@dataclass(frozen=True)
class Session:
    session_id: str
    customer: str
    month: str
    query: str
    pets: str                   # the household's declared pets: "dog cat"
    rule: str | None            # the household's declared diet: "grain-free"
    cart: tuple[str, ...]       # this month's basket, as the Shop's cart
    last_order: tuple[str, ...]  # the last order before this month
    prior_orders: int
    bought: frozenset[str]

    @property
    def slice(self) -> str:
        return history_slice(self.prior_orders)


def history_slice(prior_orders: int) -> str:
    if prior_orders == 0:
        return "0"
    if prior_orders <= 2:
        return "1-2"
    return "3-5" if prior_orders <= 5 else "6+"


def load(name: str) -> list[dict]:
    path = DATA / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing: run `./do generate-fixtures` first")
    return json.loads(path.read_text(encoding="utf-8"))


@cache
def load_products() -> dict[str, dict]:
    return {p["sku"]: p for p in load("products")}


def scored_sessions() -> list[Session]:
    """Every search session with a purchase, personas left out, in id order."""
    release = json.loads((DATA / "release-env.json").read_text(encoding="utf-8"))["counts"]
    impressions = load("impressions")
    if len(impressions) != release["impressions"]:
        raise ValueError(f"data/impressions.json has {len(impressions)} rows, the release "
                         f"{release['impressions']}: regenerate it before scoring")
    bought: dict[str, set[str]] = {}
    for row in impressions:
        if row["purchased"]:
            bought.setdefault(row["context"], set()).add(row["product_sku"])
    customers = {c["customer_id"]: c for c in load("customers")}
    order_months: dict[str, list[str]] = {}
    for order in load("orders"):
        order_months.setdefault(order["customer_id"], []).append(order["month"])
    personas = {p.customer_id for p in PERSONAS}

    sessions = []
    for c in load("contexts"):
        if c["surface"] != "search" or c["context_id"] not in bought or c["customer"] in personas:
            continue
        customer = customers[c["customer"]]
        sessions.append(Session(
            session_id=c["context_id"], customer=c["customer"], month=c["month"], query=c["search_query"],
            pets=customer.get("pets", ""), rule=customer.get("diet"),     # most declare no pet profile
            cart=tuple((c.get("basket") or "").split()), last_order=tuple((c.get("prev_basket") or "").split()),
            prior_orders=sum(1 for m in order_months.get(c["customer"], []) if m < c["month"]),
            bought=frozenset(bought[c["context_id"]]),
        ))
    return sorted(sessions, key=lambda s: s.session_id)
