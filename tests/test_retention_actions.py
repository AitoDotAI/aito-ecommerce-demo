"""Retention's ranked actions: each candidate's chance of an order, what it adds over no
action, and what it costs (ADR 0051).

A fake client answers the context read, the batched `_predict`s and each
`_estimate`, and records what it was asked.
"""

from __future__ import annotations

import pytest

from data import customer_actions as generator
from src import retention_actions
from src.aito_client import AitoError
from src.retention_actions import CANDIDATES, ranked_actions_for

CONTEXT = {"recency_bucket": "90-180d", "spend_band": "high", "offer_buyer": "mostly", "open_issue": "none",
           "email_history": "ignored", "tracking_consent": "no"}


class ActionsAito:
    """`rates` maps (action, voucher_eur) to the chance of an order; visits are twice that."""

    def __init__(self, rates, context=CONTEXT):
        self.rates, self.context = rates, context
        self.predicts: list[dict] = []
        self.estimates: list[dict] = []

    def search(self, table, where=None, limit=10, offset=0, **_):
        assert table == "action_contexts"
        ids = where["customer_id"]["$or"]
        return {"hits": [{"customer_id": cid, **self.context} for cid in ids], "total": len(ids)}

    def batch(self, queries):
        self.predicts += queries
        answers = []
        for q in queries:
            w = q["where"]
            p = self.rates[(w["action"], int(w["voucher_eur"]))]
            p = p if q["predict"] == "purchased_30d" else min(1.0, 2 * p)
            answers.append({"hits": [{"feature": True, "$p": p}, {"feature": False, "$p": 1 - p}]})
        return answers

    def estimate(self, table, where, estimate_field, model=None, with_why=True):
        self.estimates.append({"table": table, "where": where, "field": estimate_field})
        return {"estimate": 100.0}


RATES = {("none", 0): 0.10, ("email", 0): 0.10, ("discount", 0): 0.30, ("voucher", 5): 0.12, ("voucher", 10): 0.14,
         ("ad", 0): 0.10, ("apology", 5): 0.10}


def test_a_discount_that_lifts_orders_from_ten_to_thirty_percent_is_the_best_action():
    ranked = ranked_actions_for(ActionsAito(RATES), ["C1"])["C1"]
    # +0.20 × €100 of orders, less 10 % of the €100 order paid on 30 % of the customers.
    assert ranked.best == "10 % discount"
    assert ranked.options[0].net_vs_none_eur == pytest.approx(0.20 * 100 - 0.30 * 10)


def test_an_action_that_lifts_nothing_is_worth_less_than_no_action_by_its_cost():
    ranked = {o.label: o for o in ranked_actions_for(ActionsAito(RATES), ["C1"])["C1"].options}
    assert ranked["Email"].net_vs_none_eur == pytest.approx(-retention_actions.EMAIL_COST_EUR)
    assert ranked["Personalised ad"].net_vs_none_eur == pytest.approx(-retention_actions.AD_COST_EUR)
    assert ranked["No action"].net_vs_none_eur == 0


def test_a_voucher_costs_its_value_on_every_order_including_those_that_would_have_come_anyway():
    ranked = {o.label: o for o in ranked_actions_for(ActionsAito(RATES), ["C1"])["C1"].options}
    # 12 % order after a €5 voucher: 0.12 × €5 paid; the €10 voucher pays 0.14 × €10.
    assert ranked["€5 voucher"].cost_eur == pytest.approx(0.12 * 5)
    assert ranked["€10 voucher"].cost_eur == pytest.approx(0.14 * 10)


def test_no_action_is_always_among_the_options_and_everything_is_ranked_by_net():
    options = ranked_actions_for(ActionsAito(RATES), ["C1"])["C1"].options
    assert "No action" in {o.label for o in options}
    nets = [o.net_vs_none_eur for o in options]
    assert nets == sorted(nets, reverse=True)


def test_every_candidate_is_asked_for_orders_and_visits_in_the_customers_context():
    aito = ActionsAito(RATES)
    ranked_actions_for(aito, ["C1"])
    assert len(aito.predicts) == 2 * len(CANDIDATES)
    for q in aito.predicts:
        assert q["from"] == "customer_actions" and q["predict"] in ("purchased_30d", "visited_30d")
        assert {k: q["where"][k] for k in CONTEXT} == CONTEXT


def test_the_order_value_is_estimated_once_per_spend_band():
    aito = ActionsAito(RATES)
    ranked_actions_for(aito, ["C1", "C2"])
    assert aito.estimates == [{"table": "customer_actions", "where": {"spend_band": "high", "purchased_30d": True},
                               "field": "spend_30d_eur"}]


def test_a_context_value_the_table_never_saw_fails_instead_of_returning_the_base_rate():
    aito = ActionsAito(RATES, context={**CONTEXT, "open_issue": "parcel_lost"})
    with pytest.raises(AitoError, match="open_issue='parcel_lost'"):
        ranked_actions_for(aito, ["C1"])


def test_a_customer_without_a_context_row_fails_loudly():
    class NoContexts(ActionsAito):
        def search(self, table, where=None, limit=10, offset=0, **_):
            return {"hits": [], "total": 0}
    with pytest.raises(AitoError, match="No action_contexts row for customer C1"):
        ranked_actions_for(NoContexts(RATES), ["C1"])


def test_the_costs_are_the_ones_the_data_was_generated_with():
    assert (retention_actions.EMAIL_COST_EUR, retention_actions.AD_COST_EUR, retention_actions.DISCOUNT_PCT,
            retention_actions.APOLOGY_VOUCHER_EUR) == (generator.EMAIL_COST_EUR, generator.AD_COST_EUR,
                                                       generator.DISCOUNT_PCT, generator.APOLOGY_VOUCHER_EUR)
    assert {c.action for c in CANDIDATES} == set(generator.ACTIONS)
