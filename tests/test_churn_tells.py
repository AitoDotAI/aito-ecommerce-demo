"""Churn tells: the share of customers with each tell who churned, and which listed customers have which.

A fake client holds a handful of customers, orders and flagged rows, so the joins
(order lines through orders to customers) are checked, not Aito.
"""

from __future__ import annotations

import pytest

from src.churn_tells import TELLS, get_churn_tells

# C1–C4 churned. C1–C5 ordered once (a band that churned 80 %), C6–C10 three times (none churned).
CUSTOMERS = [{"customer_id": f"C{i}", "churned": i <= 4, "total_orders": 1 if i <= 5 else 3} for i in range(1, 11)]
ORDERS = [{"order_id": f"O{i}", "customer_id": f"C{i}"} for i in range(1, 11)]


class TellsAito:
    def search(self, table, where=None, limit=10, offset=0, **_):
        if table == "customers":
            hits = CUSTOMERS
        elif table == "orders":
            hits = ORDERS
        elif table == "nps_responses":
            assert where == {"nps_group": "detractor"}
            hits = [{"customer": "C1"}, {"customer": "C2"}, {"customer": "C9"}]
        elif table == "reviews":
            assert where == {"rating": {"$lte": 2}}
            hits = [{"customer_id": "C5"}]
        elif table == "order_lines":
            hits = [{"order_id": "O3"}] if where == {"returned": True} else [{"order_id": "O1"}, {"order_id": "O6"}]
        else:
            raise AssertionError(table)
        return {"hits": hits[offset:offset + limit], "total": len(hits)}


def rows():
    return {r.tell: r for r in get_churn_tells(TellsAito(), ["C1", "C9", "C10"]).rows}


def test_a_tell_is_compared_with_customers_who_ordered_as_often_not_with_everyone():
    detractor = rows()["detractor"]
    assert (detractor.customers, detractor.churners) == (3, 2)           # C1, C2 churned; C9 did not
    assert detractor.churn_rate == pytest.approx(0.667, abs=0.001)
    # C1 and C2 are in the once-ordered band (80 % churned), C9 in the three-orders band (0 %): 1.6/3 expected.
    assert detractor.expected_churn_rate == pytest.approx(0.533, abs=0.001)
    assert detractor.lift == pytest.approx(1.25)


def test_order_lines_reach_their_customer_through_the_order():
    assert rows()["returned"].customers == 1 and rows()["late_delivery"].customers == 2


def test_a_tell_no_customer_has_is_shown_with_zero_customers_not_dropped():
    assert rows()["poor_review"].customers == 1
    assert set(rows()) == set(TELLS)
    assert rows()["any"].customers == 6          # C1, C2, C9, C5, C3, C6


def test_rows_are_ordered_by_lift_and_count_the_listed_customers_who_have_the_tell():
    result = get_churn_tells(TellsAito(), ["C1", "C9", "C10"])
    lifts = [r.lift for r in result.rows]
    assert lifts == sorted(lifts, reverse=True)
    assert {r.tell: r.at_risk_listed for r in result.rows}["detractor"] == 2    # C1, C9
    assert result.tells_of == {"C1": [TELLS["detractor"], TELLS["late_delivery"]], "C9": [TELLS["detractor"]], "C10": []}
