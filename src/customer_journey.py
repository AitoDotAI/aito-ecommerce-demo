"""The journey of a segment (ADR 0059): what happened in the months around each customer's last order, for those who left and those who stayed.

A customer's journey is their events by month: visits, orders, returned lines, late or damaged deliveries, low reviews, detractor answers
to the NPS survey, and the actions the shop sent. The data is monthly, so what is known is *which months* an event fell in, not the order
within a month. Every customer is lined up on their own last order (month 0), and each cell is the share of a group with an event in the
month at that offset. For the customers who left, the months before month 0 are the months before they went quiet. The groups are the customers
of the selection that the shop counts as churned (no order in the last three months of the data) and those it does not. A segment's journey
is an aggregate: no row names or numbers a customer.
"""

from __future__ import annotations

import random
from collections import defaultdict

from src.customer_relations import MIN_GROUP, share_difference

OFFSETS = (-5, -4, -3, -2, -1, 0, 1, 2)
EVENTS = [{"code": "order", "label": "Ordered"}, {"code": "visit", "label": "Visited the shop"}, {"code": "return", "label": "Returned a line"},
          {"code": "incident", "label": "Late or damaged delivery"}, {"code": "low_review", "label": "Wrote a 1–2 star review"},
          {"code": "detractor", "label": "Answered the NPS survey 0–6"}, {"code": "action", "label": "The shop sent an action"}]
ORDER_BOUND = frozenset({"order", "return", "incident", "low_review", "detractor"})     # events that follow an order, so cannot follow a customer's last one
FOLLOW_UP_MONTHS = 3          # a control order has this many months of data after it, the window the shop calls churn
DETRACTOR_MAX = 6
LOW_REVIEW_MAX = 2


def build_events(customer_ids: set[str], orders: list[dict], order_lines: list[dict], reviews: list[dict], answers: list[dict],
                 actions: list[dict], customer_months: list[dict]) -> dict[str, dict[str, dict[str, int]]]:
    """customer -> month -> event code -> how many that month, for the asked customers. Orders are not here: the facts hold them."""
    events: dict[str, dict[str, dict[str, int]]] = {cid: defaultdict(lambda: defaultdict(int)) for cid in sorted(customer_ids)}

    def add(customer: str, month: str, code: str, n: int = 1) -> None:
        if customer in events and n:
            events[customer][month][code] += n

    owner = {o["order_id"]: (o["customer_id"], o["month"]) for o in orders if o["customer_id"] in customer_ids}
    for line in order_lines:
        if line["order_id"] in owner:
            customer, month = owner[line["order_id"]]
            add(customer, month, "return", int(bool(line["returned"])))
            add(customer, month, "incident", int(bool(line["incident"])))
    for r in reviews:
        add(r["customer_id"], r["created_at"], "low_review", int(r["rating"] <= LOW_REVIEW_MAX))
    for a in answers:
        add(a["customer"], a["month"], "detractor", int(a["score"] <= DETRACTOR_MAX))
    for a in actions:
        add(a["customer_id"], a["month"], "action", int(a["action"] != "none"))
    for v in customer_months:
        add(v["customer_id"], v["month"], "visit", int(v["visits"] > 0))
    return {cid: {m: dict(codes) for m, codes in by_month.items()} for cid, by_month in events.items()}


def journey(events: dict, customers: dict[str, dict], selected: list[str], months: list[str]) -> dict:
    """The grid for the selected customers: per event and offset, the share of those who left and of those who stayed with the event that month."""
    groups: dict[str, list[tuple[str, str, str]]] = {"churned": [], "active": []}
    without_control = 0
    for cid in selected:
        ordered = [m for m, (n, _, _) in customers[cid]["months"].items() if n > 0]
        if not ordered:
            continue
        if customers[cid]["churned"]:
            groups["churned"].append((cid, max(ordered), min(ordered)))
        elif (control := control_month(cid, customers[cid], months)) is not None:
            groups["active"].append((cid, control, min(ordered)))
        else:
            without_control += 1
    known = set(months)
    comparable = all(len(g) >= MIN_GROUP for g in groups.values())
    out = {"customers": {name: len(g) for name, g in groups.items()}, "without_control": without_control, "comparable": comparable, "offsets": list(OFFSETS), "events": EVENTS,
           "cells": {e["code"]: [_cell(e["code"], offset, groups, events, customers, known, comparable) for offset in OFFSETS] for e in EVENTS}}
    if not comparable:
        small = {name: n for name, n in out["customers"].items() if n < MIN_GROUP}
        out["reason"] = "; ".join(f"only {n} {name} customers" for name, n in small.items()) + f": a comparison needs {MIN_GROUP} in each group"
    return out


def control_month(cid: str, customer: dict, months: list[str]) -> str | None:
    """The month a customer who stayed is lined up on: one of their orders, picked at random (the same one every time) among those with at least
    `FOLLOW_UP_MONTHS` months of data after it. Lined up on their *last* order they would have no orders after it, by definition, and would
    not be a control for those who left. None if no order of theirs is old enough."""
    last_month = months[-1]
    candidates = sorted(m for m, (n, _, _) in customer["months"].items() if n > 0 and _shift(m, FOLLOW_UP_MONTHS) <= last_month)
    return random.Random(f"journey-control:{cid}").choice(candidates) if candidates else None


def _shift(month: str, n: int) -> str:
    year, number = (int(x) for x in month.split("-"))
    year, number = divmod(year * 12 + number - 1 + n, 12)
    return f"{year:04d}-{number + 1:02d}"


def _has(code: str, cid: str, month: str, events: dict, customers: dict) -> bool:
    if code == "order":
        return customers[cid]["months"].get(month, [0])[0] > 0
    return events.get(cid, {}).get(month, {}).get(code, 0) > 0


def _cell(code: str, offset: int, groups: dict, events: dict, customers: dict, known: set[str], comparable: bool) -> dict:
    counts = {}
    for name, members in groups.items():
        # A month counts for a customer only if it is a month of the data and not before their first order: before it they did not exist.
        in_data = [(cid, _shift(anchor, offset)) for cid, anchor, first in members if _shift(anchor, offset) in known and _shift(anchor, offset) >= first]
        counts[name] = (sum(_has(code, cid, month, events, customers) for cid, month in in_data), len(in_data))
    (hits_c, n_c), (hits_a, n_a) = counts["churned"], counts["active"]
    # Those who left have no order after their last one, and so no return, late delivery, review or answer that follows an order: by definition, not a finding.
    by_definition = offset > 0 and code in ORDER_BOUND
    cell = {"offset": offset, "churned": round(hits_c / n_c, 3) if n_c else None, "active": round(hits_a / n_a, 3) if n_a else None,
            "n_churned": n_c, "n_active": n_a, "points": None, "margin": None, "clear": None, "by_definition": by_definition}
    if comparable and n_c and n_a and not by_definition:
        cell["points"], cell["margin"] = share_difference(hits_c, n_c, hits_a, n_a)
        cell["clear"] = abs(cell["points"]) > cell["margin"]
    return cell
