"""Retention — who is about to leave, why, and what offer brings them back?

One view for CRM (ADR 0041), merged from Churn and Win-back. It leads
with the decision: the active customers Aito rates more likely than not
to stop ordering, the most valuable first, and the spend at stake.

  - At risk: each active customer's latest order scored by
    `_predict churned_in_3_months` over the orders whose follow-up is
    known (`churn_risk.py`). Ranked by risk × the customer's last-12-month
    spend, so the list starts where a call is worth most.
  - Why: per customer, the prediction's `$why`; across customers, the
    profiles that churn more (`churn_drivers.py`, `_relate`).
  - The offer: for each listed customer, the product email with the
    highest expected return (`winback_offer.py`).

The spend at stake is what the customers spent in the last 12 months: an
observed number, not a forecast. The risk is shown as a word ("likely",
"very likely"), not a percentage; how well the score sorts leavers from
stayers is measured in Evidence › Model checks (`churn_evaluation.py`).
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import asdict, dataclass

from src.aito_client import AitoClient
from src.catalogue_reads import read_all
from src.churn_drivers import DriverRow, get_churn_drivers
from src.churn_tells import TellRow, get_churn_tells
from src.churn_risk import LABEL_KNOWN_UNTIL, LATEST_MONTH, LIKELY, ScoredCustomer, explain, predict_body, score_active_customers
from src.retention_actions import RankedActions, ranked_actions_for
from src.retention_pets import household_pets
from src.winback_offer import EMAIL_COST_EUR, WinbackOffer, offers_for

AT_RISK_SHOWN = 20
SPEND_WINDOW_FROM = "2025-05"     # the 12 months ending LATEST_MONTH


@dataclass(frozen=True)
class AtRiskRow:
    customer_id: str
    name: str
    pets: str                      # declared, else read from their orders
    pets_declared: bool
    dog_size: str | None
    region: str
    tenure_months: int
    last_order_month: str
    latest_rating: int | None
    risk: str                      # "likely" | "very likely"
    risk_p: float                  # for the `$why` popover and the sort, not shown as a rate
    spend_12m_eur: float
    why_explanation: dict | None
    offer: WinbackOffer | None     # None: no past email sent a product for their pets
    actions: RankedActions         # every candidate action, the best first (ADR 0051)
    tells: list[str]               # what the shop observed: a detractor answer, a poor review, a return, a late delivery


@dataclass
class RetentionResponse:
    as_of_month: str
    learned_until: str              # the last month whose three months of follow-up are in the data
    decision: dict
    counts: dict
    at_risk: list[AtRiskRow]
    drivers: list[DriverRow]
    tells: list[TellRow]            # churn tells: the experience flags, by how much more of their customers churned
    driver_fields_without_effect: list[str]
    last_query: dict
    last_response_ms: int

    def to_dict(self) -> dict:
        return asdict(self)


def spend_last_12_months(client: AitoClient, customer_ids: list[str]) -> dict[str, float]:
    rows = read_all(client, "customer_months", where={
        "customer_id": {"$or": customer_ids}, "month": {"$gte": SPEND_WINDOW_FROM}})
    spend = {cid: 0.0 for cid in customer_ids}
    for row in rows:
        spend[row["customer_id"]] += float(row["spent_eur"])
    return spend


def get_retention(client: AitoClient) -> RetentionResponse:
    started = time.perf_counter()
    scored = score_active_customers(client)
    likely = [c for c in scored if c.risk_p >= LIKELY]
    spend = spend_last_12_months(client, [c.customer_id for c in likely]) if likely else {}
    shown = sorted(likely, key=lambda c: -c.risk_p * spend[c.customer_id])[:AT_RISK_SHOWN]
    whys = explain(client, shown)
    pets = household_pets(client, shown)
    offers = offers_for(client, {cid: p.split() for cid, p in pets.items()})
    tells = get_churn_tells(client, [c.customer_id for c in shown])
    actions = ranked_actions_for(client, [c.customer_id for c in shown]) if shown else {}
    rows = [_row(c, pets[c.customer_id], spend[c.customer_id], whys[c.customer_id], offers[c.customer_id], actions[c.customer_id], tells.tells_of[c.customer_id])
            for c in shown]
    drivers = get_churn_drivers(client)
    churned = client.search("customers", where={"churned": True}, limit=0)["total"]

    return RetentionResponse(
        as_of_month=LATEST_MONTH,
        learned_until=LABEL_KNOWN_UNTIL,
        decision={
            "customers": len(rows),
            "spend_12m_eur": round(sum(r.spend_12m_eur for r in rows), 2),
            "offers": sum(r.offer is not None for r in rows),
            "offers_expected_return_eur": round(sum(r.offer.expected_return_eur for r in rows if r.offer), 2),
            "email_cost_eur": EMAIL_COST_EUR,
            "best_actions": dict(Counter(r.actions.best for r in rows)),
            "best_actions_net_eur": round(sum(r.actions.options[0].net_vs_none_eur for r in rows), 2),
        },
        counts={"active": len(scored), "likely_to_leave": len(likely), "churned": churned},
        at_risk=rows,
        drivers=drivers.drivers,
        tells=tells.rows,
        driver_fields_without_effect=drivers.fields_without_effect,
        last_query={"endpoint": "_predict", "body": predict_body(shown[0].evidence)} if shown else
        {"endpoint": "_predict", "body": {"note": "No active customer is likely to leave."}},
        last_response_ms=int((time.perf_counter() - started) * 1000),
    )


def _row(c: ScoredCustomer, pets: str, spend: float, why: dict | None, offer: WinbackOffer | None,
         actions: RankedActions, tells: list[str]) -> AtRiskRow:
    return AtRiskRow(
        customer_id=c.customer_id, name=c.name, pets=pets, pets_declared=c.pets is not None, dog_size=c.dog_size, region=c.region,
        tenure_months=c.tenure_months, last_order_month=c.last_order_month,
        latest_rating=c.latest_rating, risk=c.risk, risk_p=c.risk_p,
        spend_12m_eur=round(spend, 2), why_explanation=why, offer=offer, actions=actions, tells=tells,
    )
