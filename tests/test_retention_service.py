"""Retention's decision: who to reach first, and the spend at stake.

The Aito parts (the churn scan, its `$why`, the offers, the drivers) are
replaced with fixed answers, so this checks how the view composes them.
"""

from __future__ import annotations

import pytest

from src import retention_service
from src.churn_drivers import ChurnDrivers
from src.churn_risk import ScoredCustomer
from src.winback_offer import WinbackOffer


def _scored(cid: str, risk_p: float) -> ScoredCustomer:
    return ScoredCustomer(customer_id=cid, name=cid, pets="cat", dog_size=None, region="oulu",
                          last_order_month="2026-03", tenure_months=6, visits=2, latest_rating=None,
                          risk_p=risk_p, evidence={"pets": "cat", "purchases": 1})


SCORED = [_scored("SAFE", 0.1), _scored("RISKY_SMALL", 0.9), _scored("RISKY_BIG", 0.6)]
SPEND = {"RISKY_SMALL": 100.0, "RISKY_BIG": 900.0}
OFFER = WinbackOffer(sku="FOOD", name="Food", category="cat/dry-food", price_eur=10.0,
                     response_p=0.2, order_value_eur=50.0, expected_return_eur=9.5)


class CountOnly:
    def search(self, table, where=None, limit=10, **_):
        return {"hits": [], "total": 7}


@pytest.fixture
def retention(monkeypatch):
    monkeypatch.setattr(retention_service, "score_active_customers", lambda client: SCORED)
    monkeypatch.setattr(retention_service, "spend_last_12_months", lambda client, ids: {i: SPEND[i] for i in ids})
    monkeypatch.setattr(retention_service, "explain", lambda client, cs: {c.customer_id: None for c in cs})
    monkeypatch.setattr(retention_service, "offers_for", lambda client, pets: {cid: OFFER for cid in pets})
    monkeypatch.setattr(retention_service, "get_churn_drivers", lambda client: ChurnDrivers([], ["diet"]))
    return retention_service.get_retention(CountOnly())


def test_only_customers_more_likely_to_leave_than_not_are_listed(retention):
    assert {r.customer_id for r in retention.at_risk} == {"RISKY_SMALL", "RISKY_BIG"}
    assert retention.counts == {"active": 3, "likely_to_leave": 2, "churned": 7}


def test_the_list_starts_where_the_most_spend_is_at_risk(retention):
    # 0.6 × €900 outranks 0.9 × €100: a call is worth more there.
    assert [r.customer_id for r in retention.at_risk] == ["RISKY_BIG", "RISKY_SMALL"]
    assert [r.risk for r in retention.at_risk] == ["likely", "very likely"]


def test_the_decision_sums_observed_spend_and_the_offers_expected_return(retention):
    assert retention.decision["customers"] == 2
    assert retention.decision["spend_12m_eur"] == 1000.0
    assert retention.decision["offers"] == 2
    assert retention.decision["offers_expected_return_eur"] == 19.0
