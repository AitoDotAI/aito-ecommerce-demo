"""Churn tells: what a customer went through just before, read against who left after.

`churn_drivers` relates the profile (pets, region, tenure). These are what
the shop observed about the customer's experience in the last three months:
an NPS answer as a detractor, a 1–2 star review, a returned item, a late or
damaged delivery.

The question is asked on the churn panel (`customer_months`, one row per
customer per month, labelled `churned_in_3_months`), restricted to rows where
the customer ordered in the last three months. Without that restriction a
tell can only exist in a month with an order, so every tell would look
protective: the customer who leaves has stopped ordering. With it, each row
reads as "among customers who had just ordered, 20 % of those with this tell
stopped within three months, against 15 % of those without". Observed
shares, not a cause, and one customer's months overlap, so the counts are
customer-months.

The tables are small, so each flag is one filtered read, joined in Python
(`order_lines` reach their month through `orders`).
"""

from __future__ import annotations

from dataclasses import dataclass

from src.aito_client import AitoClient
from src.catalogue_reads import read_all
from src.churn_risk import LATEST_MONTH

WINDOW_MONTHS = 3

TELLS: dict[str, str] = {
    "detractor": "Answered the NPS survey as a detractor (0–6)",
    "poor_review": "Wrote a 1–2 star review",
    "returned": "Returned an item",
    "late_delivery": "Had a late or damaged delivery",
}
ANY = "Any of the four"
# The raw answer, by band: a score of 0–3 is a customer who is done, 9–10 one who is not.
SCORE_BANDS: dict[str, tuple[str, int, int]] = {
    "nps_0_3": ("Answered the NPS survey 0–3", 0, 3),
    "nps_4_6": ("Answered the NPS survey 4–6", 4, 6),
    "nps_7_8": ("Answered the NPS survey 7–8", 7, 8),
    "nps_9_10": ("Answered the NPS survey 9–10", 9, 10),
}


@dataclass(frozen=True)
class TellRow:
    tell: str
    label: str
    customer_months: int       # months of customers who had just ordered, with this tell in the last 3 months
    churned: int               # of which the customer stopped within 3 months
    churn_rate: float
    churn_rate_without: float  # the same, for months without it
    lift: float                # churn_rate / churn_rate_without
    at_risk_listed: int = 0    # of the customers Retention lists, how many have it now


@dataclass(frozen=True)
class ChurnTells:
    rows: list[TellRow]
    tells_of: dict[str, list[str]]     # customer id → labels of the tells they have now


def month_number(month: str) -> int:
    year, number = month.split("-")
    return int(year) * 12 + int(number)


def tell_months(client: AitoClient) -> dict[str, dict[str, set[int]]]:
    """tell → customer id → the months (as numbers) it happened in."""
    order_of = {o["order_id"]: (o["customer_id"], month_number(o["month"])) for o in read_all(client, "orders")}
    found: dict[str, dict[str, set[int]]] = {tell: {} for tell in [*TELLS, *SCORE_BANDS]}

    def add(tell: str, customer_id: str, month: int) -> None:
        found[tell].setdefault(customer_id, set()).add(month)

    for r in read_all(client, "nps_responses"):
        if r["nps_group"] == "detractor":
            add("detractor", r["customer"], month_number(r["month"]))
        for band, (_, low, high) in SCORE_BANDS.items():
            if low <= r["score"] <= high:
                add(band, r["customer"], month_number(r["month"]))
    for r in read_all(client, "reviews", where={"rating": {"$lte": 2}}):
        add("poor_review", r["customer_id"], month_number(r["created_at"]))
    for tell, field in (("returned", "returned"), ("late_delivery", "incident")):
        for r in read_all(client, "order_lines", where={field: True}):
            customer_id, month = order_of[r["order_id"]]
            add(tell, customer_id, month)
    return found


def _within_window(months: set[int], at: int) -> bool:
    return any(at - WINDOW_MONTHS < m <= at for m in months)


def get_churn_tells(client: AitoClient, listed_ids: list[str]) -> ChurnTells:
    found = tell_months(client)
    # The last months have no label yet (the three months after them are not in the data): those
    # rows stay out of the comparison, and are counted by nothing here.
    panel = [r for r in read_all(client, "customer_months") if r["churned_in_3_months"] is not None]
    ordered_months: dict[str, set[int]] = {}
    for r in panel:
        if r["purchases"] > 0:
            ordered_months.setdefault(r["customer_id"], set()).add(month_number(r["month"]))
    rows_ = [(r, month_number(r["month"])) for r in panel]
    rows_ = [(r, at) for r, at in rows_ if _within_window(ordered_months.get(r["customer_id"], set()), at)]

    def has(tell: str, customer_id: str, at: int) -> bool:
        return _within_window(found[tell].get(customer_id, set()), at)

    rows = []
    labelled = [*TELLS.items(), ("any", ANY), *[(band, spec[0]) for band, spec in SCORE_BANDS.items()]]
    for tell, label in labelled:
        flags = [any(has(t, r["customer_id"], at) for t in TELLS) if tell == "any" else has(tell, r["customer_id"], at)
                 for r, at in rows_]
        with_, without = [r for (r, _), f in zip(rows_, flags) if f], [r for (r, _), f in zip(rows_, flags) if not f]
        rate = sum(bool(r["churned_in_3_months"]) for r in with_) / len(with_) if with_ else 0.0
        rate_without = sum(bool(r["churned_in_3_months"]) for r in without) / len(without) if without else 0.0
        now = month_number(LATEST_MONTH)
        listed = sum(any(has(t, cid, now) for t in (TELLS if tell == "any" else [tell])) for cid in listed_ids)
        rows.append(TellRow(tell=tell, label=label, customer_months=len(with_),
                            churned=sum(bool(r["churned_in_3_months"]) for r in with_),
                            churn_rate=round(rate, 3), churn_rate_without=round(rate_without, 3),
                            lift=round(rate / rate_without, 2) if rate_without else 0.0, at_risk_listed=listed))
    rows.sort(key=lambda r: -r.lift)
    now = month_number(LATEST_MONTH)
    tells_of = {cid: [TELLS[t] for t in TELLS if has(t, cid, now)] for cid in listed_ids}
    return ChurnTells(rows=rows, tells_of=tells_of)
