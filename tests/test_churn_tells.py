"""Churn tells: among customers who had just ordered, the churn after a tell against the churn without one.

A fake client holds a small churn panel and flagged rows, so the joins (order lines through
orders to a month, a tell's three-month window, the "had just ordered" restriction) are checked, not Aito.
"""

from __future__ import annotations

import pytest

from src.churn_tells import TELLS, get_churn_tells

# Months 2026-01 .. 2026-04 for customers C1–C5; the label is unknown (None) for 2026-04. C5 never ordered.
PANEL = []
for cid, bought, label in [("C1", [1, 1, 1, 1], True), ("C2", [1, 1, 1, 1], False), ("C3", [1, 0, 0, 0], False),
                           ("C4", [1, 1, 1, 1], False), ("C5", [0, 0, 0, 0], True)]:
    for i, month in enumerate(["2026-01", "2026-02", "2026-03", "2026-04"]):
        PANEL.append({"customer_id": cid, "month": month, "purchases": bought[i],
                      "churned_in_3_months": None if month == "2026-04" else label})
ORDERS = [{"order_id": "O1", "customer_id": "C1", "month": "2026-01"}, {"order_id": "O2", "customer_id": "C2", "month": "2026-02"}]


class TellsAito:
    def search(self, table, where=None, limit=10, offset=0, **_):
        hits = {
            "customer_months": PANEL, "orders": ORDERS,
            "nps_responses": [{"customer": "C1", "month": "2026-02"}],        # C1: a detractor in February
            "reviews": [],
            "order_lines": [{"order_id": "O1"}] if where == {"returned": True} else [{"order_id": "O2"}],
        }[table]
        return {"hits": hits[offset:offset + limit], "total": len(hits)}


def rows():
    return {r.tell: r for r in get_churn_tells(TellsAito(), ["C1", "C2"]).rows}


def test_a_tell_lasts_three_months_and_is_compared_with_months_that_had_none():
    detractor = rows()["detractor"]
    # C1's answer in 2026-02 is in the window of 2026-02, -03 and -04; -04 has no label: 2 months, both churned.
    assert (detractor.customer_months, detractor.churned) == (2, 2)
    # Without it: C1 January (churned) and the three labelled months of C2, C3 and C4 (stayed) = 1 of 10.
    assert detractor.churn_rate == 1.0 and detractor.churn_rate_without == pytest.approx(0.1)
    assert detractor.lift == 10.0


def test_months_of_customers_who_had_not_just_ordered_are_left_out_of_both_sides():
    # C5 never ordered and "churned" in every labelled month. Counted, the months without a tell would be
    # 4 of 13 and the lift 3.25; left out, 1 of 10.
    assert rows()["detractor"].churn_rate_without == pytest.approx(0.1)


def test_order_lines_reach_their_month_through_the_order():
    # O1 (C1, January) is in the window of January, February and March; O2 (C2, February) of February and March.
    assert rows()["returned"].customer_months == 3 and rows()["late_delivery"].customer_months == 2


def test_every_tell_is_listed_and_rows_are_ordered_by_lift():
    result = get_churn_tells(TellsAito(), ["C1", "C2"])
    assert {r.tell for r in result.rows} == set(TELLS) | {"any"}
    lifts = [r.lift for r in result.rows]
    assert lifts == sorted(lifts, reverse=True)


def test_the_listed_customers_carry_the_tells_they_have_now():
    # "Now" is 2026-04, whose window is February to April: C1's February answer and C2's February late delivery,
    # not C1's January return.
    assert get_churn_tells(TellsAito(), ["C1", "C2"]).tells_of == {
        "C1": [TELLS["detractor"]], "C2": [TELLS["late_delivery"]]}
