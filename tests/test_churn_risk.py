"""Retention's churn score: what Aito learns from, and what it scores.

A fake client answers the reads and the batched `_predict`s, and records
each body, so these tests pin the query: the population of orders whose
three months after are known, and each active customer's latest order as
the evidence. The live behaviour is asserted in `test_aito_check.py`.
"""

from __future__ import annotations

import pytest

from src.aito_client import AitoError
from src.churn_risk import LABEL_KNOWN_UNTIL, explain, score_active_customers


def _customer(cid: str, last_order: str) -> dict:
    return {"customer_id": cid, "name": f"Name {cid}", "pets": "cat", "region": "oulu",
            "last_order_month": last_order, "churned": False}


def _month(cid: str, month: str, **fields) -> dict:
    return {"customer_month_id": f"{cid}-{month}", "customer_id": cid, "month": month, "pets": "cat",
            "region": "oulu", "tenure_months_at_month": 5, "visits": 3, "purchases": 0, "spent_eur": 0.0,
            "dog_size": None, "latest_rating": None, **fields}


ACTIVE = [_customer("C1", "2026-02"), _customer("C2", "2026-04")]
MONTHS = [_month("C1", "2026-02", purchases=1, spent_eur=40.0), _month("C1", "2026-03"), _month("C1", "2026-04"),
          _month("C2", "2026-04", purchases=2, spent_eur=80.0, visits=9)]


class ChurnAito:
    def __init__(self, months=MONTHS, risk=None):
        self.months = months
        self.risk = risk or {"C1": 0.7, "C2": 0.1}
        self.searches: list[tuple[str, dict | None]] = []
        self.batches: list[list[dict]] = []

    def search(self, table, where=None, limit=10, offset=0, **_):
        self.searches.append((table, where))
        rows = ACTIVE if table == "customers" else self.months
        return {"hits": rows[offset:offset + limit], "total": len(rows)}

    def batch(self, queries):
        self.batches.append(queries)
        answers = []
        for q in queries:
            cid = "C1" if q["where"]["purchases"] == 1 else "C2"
            p = self.risk[cid]
            answers.append({"hits": [{"feature": True, "$p": p, "$why": None},
                                     {"feature": False, "$p": 1 - p}]})
        return answers


def test_aito_learns_only_from_orders_whose_next_three_months_are_known():
    fake = ChurnAito()

    score_active_customers(fake)

    body = fake.batches[0][0]
    # A nested `from` sets the population: a month in which the customer
    # ordered, up to the last month with three months of follow-up.
    assert body["from"] == {"from": "customer_months",
                            "where": {"month": {"$lte": LABEL_KNOWN_UNTIL}, "purchases": {"$gte": 1}}}
    assert body["predict"] == "churned_in_3_months"


def test_each_active_customer_is_scored_on_the_month_of_their_latest_order():
    fake = ChurnAito()

    scored = {c.customer_id: c for c in score_active_customers(fake)}

    # C1 last ordered in February: the quiet March and April rows are not the evidence.
    sent = [q["where"] for q in fake.batches[0]]
    assert {(w["purchases"], w["spent_eur"]) for w in sent} == {(1, 40.0), (2, 80.0)}
    assert scored["C1"].risk_p == 0.7 and scored["C1"].risk == "likely"
    assert scored["C2"].risk == "unlikely"
    # Empty nullable fields are left out of the evidence: Aito refuses `null`.
    assert all("dog_size" not in w and "latest_rating" not in w for w in sent)


def test_the_scan_asks_no_why_and_the_listed_customers_are_explained_in_one_batch():
    fake = ChurnAito()
    scored = score_active_customers(fake)
    assert fake.batches[0][0]["select"] == ["$p", "feature"]

    explain(fake, scored[:1])

    [why_batch] = fake.batches[1:]
    assert len(why_batch) == 1 and "$why" in str(why_batch[0]["select"])


def test_an_active_customer_without_a_row_for_their_last_order_is_an_error():
    fake = ChurnAito(months=[m for m in MONTHS if m["customer_id"] != "C2"])

    with pytest.raises(AitoError, match="no customer_months row"):
        score_active_customers(fake)
