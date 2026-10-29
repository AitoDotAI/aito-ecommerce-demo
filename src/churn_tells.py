"""Churn tells: what customers who left had in common, beyond who they are.

`churn_drivers` relates the profile (pets, region, tenure). These are what
the shop observed about the customer's experience: an NPS answer as a
detractor, a 1–2 star review, a returned item, a late or damaged delivery.
Each is a customer-level flag ("ever"). A customer who orders more has more
chances to have any of them, and customers who stay order more, so the plain
shares make every tell look protective (0.76–0.96× on release 3b). Each
row therefore compares the tell's customers with customers who ordered as
often: the churn the same mix of order counts would have had is what the
lift is taken against. They are observed shares, not a cause.

The tables are small, so each flag is one filtered read, joined to the
customer in Python (`order_lines` reach the customer through `orders`).
"""

from __future__ import annotations

from dataclasses import dataclass

from src.aito_client import AitoClient
from src.catalogue_reads import read_all

TELLS: dict[str, str] = {
    "detractor": "Answered the NPS survey as a detractor (0–6)",
    "poor_review": "Wrote a 1–2 star review",
    "returned": "Returned an item",
    "late_delivery": "Had a late or damaged delivery",
    "any": "Any of the four",
}


@dataclass(frozen=True)
class TellRow:
    tell: str
    label: str
    customers: int             # customers with this tell
    churners: int              # of whom churned
    churn_rate: float
    expected_churn_rate: float  # what customers with as many orders churned at
    lift: float                # churn_rate / expected_churn_rate
    at_risk_listed: int = 0    # of the customers Retention lists now, how many have it


@dataclass(frozen=True)
class ChurnTells:
    rows: list[TellRow]
    tells_of: dict[str, list[str]]     # customer id → labels of the tells they have


def order_count_band(total_orders: int) -> str:
    return "1" if total_orders <= 1 else "2" if total_orders == 2 else "3-4" if total_orders <= 4 else "5-8" if total_orders <= 8 else "9+"


def customers_with_tells(client: AitoClient) -> dict[str, set[str]]:
    orders = {o["order_id"]: o["customer_id"] for o in read_all(client, "orders")}
    by_tell = {
        "detractor": {r["customer"] for r in read_all(client, "nps_responses", where={"nps_group": "detractor"})},
        "poor_review": {r["customer_id"] for r in read_all(client, "reviews", where={"rating": {"$lte": 2}})},
        "returned": {orders[r["order_id"]] for r in read_all(client, "order_lines", where={"returned": True})},
        "late_delivery": {orders[r["order_id"]] for r in read_all(client, "order_lines", where={"incident": True})},
    }
    assert set(by_tell) | {"any"} == set(TELLS), set(by_tell) ^ set(TELLS)
    return by_tell


def get_churn_tells(client: AitoClient, listed_ids: list[str]) -> ChurnTells:
    customers = read_all(client, "customers")
    band_of = {c["customer_id"]: order_count_band(c["total_orders"]) for c in customers}
    churned = {c["customer_id"] for c in customers if c["churned"]}
    members: dict[str, list[str]] = {}
    for cid, band in band_of.items():
        members.setdefault(band, []).append(cid)
    band_churn_rate = {band: sum(cid in churned for cid in ids) / len(ids) for band, ids in members.items()}
    by_tell = customers_with_tells(client)
    by_tell["any"] = set().union(*by_tell.values())
    rows = []
    for tell, label in TELLS.items():
        have = by_tell[tell]
        expected = sum(band_churn_rate[band_of[cid]] for cid in have) / len(have) if have else 0.0
        rate = len(have & churned) / len(have) if have else 0.0
        rows.append(TellRow(tell=tell, label=label, customers=len(have), churners=len(have & churned),
                            churn_rate=round(rate, 3), expected_churn_rate=round(expected, 3),
                            lift=round(rate / expected, 2) if expected else 0.0,
                            at_risk_listed=sum(cid in have for cid in listed_ids)))
    rows.sort(key=lambda r: -r.lift)
    tells_of = {cid: [TELLS[t] for t in TELLS if t != "any" and cid in by_tell[t]] for cid in listed_ids}
    return ChurnTells(rows=rows, tells_of=tells_of)
