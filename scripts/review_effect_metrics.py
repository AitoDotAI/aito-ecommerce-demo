"""The metrics of ADR 0039's planted effects: quality → experience → reviews, NPS, churn, demand.

Read from one generated data dir and its answer key (each line's experience,
each customer's churn month); `scripts/planted_effects.py` compares them
between a planted generation and its null
(docs/verification/actionable-states-prereg.md).
"""
from __future__ import annotations

import json
from collections import defaultdict
from functools import cache

from data.catalogue_events import add_months
from data.review_chain import order_experience, quality
from scripts.planted_effect_metrics import Fixtures, _rate

LAST_CHURN_LABEL_MONTH = "2026-01"     # 3 months of churn after it fit before 2026-04
CHURN_WINDOW = 3


@cache
def _orders(fx: Fixtures) -> dict[str, dict]:
    """order_id → the order, with its experience (its worst line's) and its reviews."""
    experience = {row["line_id"]: row["experience"]
                  for row in json.loads((fx.dir / "answer_key" / "line_experiences.json").read_text())}
    lines_of: dict[str, list[str]] = defaultdict(list)
    for ln in fx.load("order_lines"):
        lines_of[ln["order_id"]].append(ln["line_id"])
    reviews_of: dict[str, list[dict]] = defaultdict(list)
    order_of_line = {ln["line_id"]: ln["order_id"] for ln in fx.load("order_lines")}
    for r in fx.load("reviews"):
        reviews_of[order_of_line[r["order_line"]]].append(r)
    return {o["order_id"]: {**o, "experience": order_experience([experience[i] for i in lines_of[o["order_id"]]]),
                            "reviews": reviews_of[o["order_id"]]}
            for o in fx.load("orders")}


def _churns_within(fx: Fixtures, customer: str, month: str) -> bool:
    churn = fx.traits()[customer].get("churn_month")
    return churn is not None and month < churn <= add_months(month, CHURN_WINDOW)


def stars_contrast(fx: Fixtures, outcome: str) -> float:
    """R1 (clicked), R2a (purchased): the outcome's rate at 5 stars ÷ at 1–2."""
    state = fx.state()
    rows = fx.impressions()
    return (_rate((r for r in rows if state[r["product_state"]]["rating_band"] == "5"), outcome)
            / _rate((r for r in rows if state[r["product_state"]]["rating_band"] == "1-2"), outcome))


def poor_quality_contrast(fx: Fixtures) -> float:
    """R2b: purchase rate of poor-quality products ÷ the rest."""
    rows = fx.impressions()
    return (_rate(r for r in rows if quality(r["product_sku"]) == "poor")
            / _rate(r for r in rows if quality(r["product_sku"]) != "poor"))


def _nps_after(fx: Fixtures, keep) -> list[int]:
    orders = _orders(fx)
    return [a["score"] for a in fx.load("nps_responses") if keep(orders[a["surveyed_order"]])]


def _mean(values: list[float]) -> float:
    assert values, "nothing to average"
    return sum(values) / len(values)


def nps_after_bad(fx: Fixtures) -> float:
    """R3a: mean NPS of answers about a bad-experience order."""
    return _mean(_nps_after(fx, lambda o: o["experience"] == "bad"))


def nps_after_bad_without_review(fx: Fixtures) -> float:
    """R3b: the same, for buyers who reviewed nothing in that order."""
    return _mean(_nps_after(fx, lambda o: o["experience"] == "bad" and not o["reviews"]))


def nps_reviewer_gap(fx: Fixtures) -> float:
    """R3b: after a bad order, buyers who reviewed it without a reply − buyers who didn't review."""
    reviewed = _nps_after(fx, lambda o: o["experience"] == "bad" and o["reviews"]
                          and not any(r["replied"] for r in o["reviews"]))
    return _mean(reviewed) - nps_after_bad_without_review(fx)


def nps_reply_gap(fx: Fixtures) -> float:
    """R3c: writers of a negative review of the surveyed order, with a reply − without."""
    negative = lambda o: [r for r in o["reviews"] if r["rating"] <= 2]
    replied = _nps_after(fx, lambda o: any(r["replied"] for r in negative(o)))
    unreplied = _nps_after(fx, lambda o: negative(o) and not any(r["replied"] for r in negative(o)))
    return _mean(replied) - _mean(unreplied)


def churn_after_bad(fx: Fixtures) -> float:
    """R4a: P(the customer churns in the 3 months after a bad-experience order)."""
    bad = [o for o in _orders(fx).values() if o["experience"] == "bad" and o["month"] <= LAST_CHURN_LABEL_MONTH]
    return sum(_churns_within(fx, o["customer_id"], o["month"]) for o in bad) / len(bad)


def churn_after_incident(fx: Fixtures) -> float:
    """A6: P(the customer churns in the 3 months after an order with a late or damaged delivery)."""
    incident_orders = {ln["order_id"] for ln in fx.load("order_lines") if ln["incident"]}
    orders = [o for oid, o in _orders(fx).items() if oid in incident_orders and o["month"] <= LAST_CHURN_LABEL_MONTH]
    return sum(_churns_within(fx, o["customer_id"], o["month"]) for o in orders) / len(orders)


def churn_after_return(fx: Fixtures) -> float:
    """A7: P(the customer churns in the 3 months after an order with a returned line)."""
    returned_orders = {ln["order_id"] for ln in fx.load("order_lines") if ln["returned"]}
    orders = [o for oid, o in _orders(fx).items() if oid in returned_orders and o["month"] <= LAST_CHURN_LABEL_MONTH]
    return sum(_churns_within(fx, o["customer_id"], o["month"]) for o in orders) / len(orders)


def returned_after_bad(fx: Fixtures) -> float:
    """A7: share of lines whose experience was bad that were returned."""
    experience = {row["line_id"]: row["experience"]
                  for row in json.loads((fx.dir / "answer_key" / "line_experiences.json").read_text())}
    bad = [ln for ln in fx.load("order_lines") if experience[ln["line_id"]] == "bad"]
    return sum(ln["returned"] for ln in bad) / len(bad)


def churn_by_last_nps(fx: Fixtures) -> float:
    """A9: churned share of customers whose last NPS answer was 0–3 ÷ of those whose last answer was 9–10."""
    last = {}
    for r in sorted(fx.load("nps_responses"), key=lambda r: r["month"]):
        last[r["customer"]] = r["score"]
    churned = {c["customer_id"]: c["churned"] for c in fx.load("customers")}
    share = lambda ids: sum(churned[c] for c in ids) / len(ids)
    return share([c for c, s in last.items() if s <= 3]) / share([c for c, s in last.items() if s >= 9])


def churn_after_replied_counts(fx: Fixtures) -> tuple[int, int]:
    """R4b: (writers who churned in the 3 months after a replied negative review, writers)."""
    replied = [r for r in fx.load("reviews") if r["replied"] and r["created_at"] <= LAST_CHURN_LABEL_MONTH]
    return sum(_churns_within(fx, r["customer_id"], r["created_at"]) for r in replied), len(replied)


def never_ordered_again_after_bad(fx: Fixtures) -> float:
    """R4c: share of bad-experience orders after which the customer never ordered again (and churned)."""
    churned = {c["customer_id"]: c for c in fx.load("customers")}
    bad = [o for o in _orders(fx).values() if o["experience"] == "bad" and o["month"] <= LAST_CHURN_LABEL_MONTH]
    gone = [o for o in bad if churned[o["customer_id"]]["churned"]
            and churned[o["customer_id"]]["last_order_month"] == o["month"]]
    return len(gone) / len(bad)


def _units_by_band(fx: Fixtures):
    state = fx.state()
    units: dict[str, list[tuple[bool, int]]] = defaultdict(list)
    for ms in fx.load("monthly_sales"):
        st = state[ms["product_state"]]
        units[st["rating_band"]].append((st["on_offer"], ms["units_sold"]))
    return units


def demand_by_stars(fx: Fixtures) -> float:
    """R5: units per state-month at 5 stars ÷ at 1–2."""
    units = _units_by_band(fx)
    return _mean([u for _, u in units["5"]]) / _mean([u for _, u in units["1-2"]])


def offer_response_by_stars(fx: Fixtures) -> float:
    """R6: (units on offer ÷ off offer, per state-month) at 1–2 stars ÷ the same at 5 stars."""
    units = _units_by_band(fx)

    def response(band: str) -> float:
        return (_mean([u for on, u in units[band] if on]) / _mean([u for on, u in units[band] if not on]))

    return response("1-2") / response("5")


def clear_caches() -> None:
    _orders.cache_clear()
