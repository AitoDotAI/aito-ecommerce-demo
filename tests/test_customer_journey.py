"""The journey of a segment (ADR 0059): what happened in the months around each customer's last order, those who left against those who stayed."""

import pytest

from src.customer_journey import EVENTS, OFFSETS, build_events, journey

MONTHS = [f"2026-{m:02d}" for m in range(1, 13)]


def customer(last_order: str, churned: bool, first_order: str | None = None) -> dict:
    orders = {m: [1, 10.0, 5.0] for m in (first_order, last_order) if m}
    return {"churned": churned, "months": orders}


def test_events_are_counted_per_customer_and_month_from_the_shops_tables():
    orders = [{"order_id": "O1", "customer_id": "C1", "month": "2026-03"}]
    lines = [{"order_id": "O1", "returned": True, "incident": True}, {"order_id": "O1", "returned": False, "incident": True}]
    reviews = [{"customer_id": "C1", "created_at": "2026-03", "rating": 1}, {"customer_id": "C1", "created_at": "2026-03", "rating": 5}]
    answers = [{"customer": "C1", "month": "2026-03", "score": 4}, {"customer": "C1", "month": "2026-04", "score": 10}]
    actions = [{"customer_id": "C1", "month": "2026-04", "action": "email"}, {"customer_id": "C1", "month": "2026-04", "action": "none"}]
    visits = [{"customer_id": "C1", "month": "2026-03", "visits": 3}, {"customer_id": "C1", "month": "2026-04", "visits": 0}]

    events = build_events({"C1"}, orders, lines, reviews, answers, actions, visits)

    assert events["C1"]["2026-03"] == {"return": 1, "incident": 2, "low_review": 1, "detractor": 1, "visit": 1}
    assert events["C1"]["2026-04"] == {"action": 1}, "no action is not an action; a promoter and a month with no visits are not events"


def test_events_of_customers_outside_the_asked_ones_are_not_kept():
    events = build_events({"C1"}, [{"order_id": "O1", "customer_id": "C9", "month": "2026-03"}], [], [{"customer_id": "C9", "created_at": "2026-03", "rating": 1}], [], [], [])

    assert events == {"C1": {}}


def test_each_cell_is_the_share_of_customers_with_the_event_that_month_relative_to_their_last_order_for_those_who_left_and_those_who_stayed():
    customers = {f"L{i}": customer("2026-06", True, "2026-01") for i in range(40)} | {f"S{i}": customer("2026-09", False, "2026-01") for i in range(40)}
    events = {f"L{i}": {"2026-05": {"return": 1}} for i in range(30)} | {f"L{i}": {} for i in range(30, 40)}
    events |= {f"S{i}": {"2026-08": {"return": 1}} for i in range(4)} | {f"S{i}": {} for i in range(4, 40)}

    result = journey(events, customers, list(customers), MONTHS)

    assert result["customers"] == {"churned": 40, "active": 40}
    cell = next(c for c in result["cells"]["return"] if c["offset"] == -1)
    assert cell["churned"] == 0.75 and cell["active"] == 0.1
    assert cell["points"] == pytest.approx(65.0) and cell["clear"] is True


def test_a_month_outside_the_data_is_not_counted_for_the_customer_whose_offset_falls_there():
    customers = {f"S{i}": customer("2026-12", False, "2026-01") for i in range(40)} | {f"L{i}": customer("2026-06", True, "2026-01") for i in range(40)}

    result = journey({c: {} for c in customers}, customers, list(customers), MONTHS)

    after = next(c for c in result["cells"]["order"] if c["offset"] == 1)
    assert after["n_active"] == 0 and after["active"] is None and after["clear"] is None, "December is the last month: nobody has a month after it"
    assert after["n_churned"] == 40


def test_the_offsets_run_from_five_months_before_the_last_order_to_two_after():
    assert OFFSETS == (-5, -4, -3, -2, -1, 0, 1, 2)
    assert [e["code"] for e in EVENTS] == ["order", "visit", "return", "incident", "low_review", "detractor", "action"]


def test_a_group_with_too_few_customers_is_not_compared():
    customers = {f"L{i}": customer("2026-06", True) for i in range(40)} | {f"S{i}": customer("2026-09", False) for i in range(5)}

    result = journey({c: {} for c in customers}, customers, list(customers), MONTHS)

    assert result["comparable"] is False and "5" in result["reason"]


def test_the_last_order_month_is_the_last_month_with_an_order_and_a_customer_without_orders_is_left_out():
    customers = {"A": customer("2026-04", True, "2026-01"), "B": {"churned": False, "months": {}}}

    result = journey({"A": {}, "B": {}}, customers, ["A", "B"], MONTHS)

    assert result["customers"] == {"churned": 1, "active": 0}


def api():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from src.customer_profile_routes import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_the_route_serves_the_journey_of_everyone_and_of_a_segment_and_refuses_a_bad_condition():
    everyone = api().get("/api/customer-profiles/journey").json()
    dogs = api().get("/api/customer-profiles/journey", params={"c": "pets:dog"}).json()

    assert everyone["comparable"] is True and everyone["customers"]["churned"] > 0 and everyone["customers"]["active"] > 0
    assert everyone["customers"]["churned"] + everyone["customers"]["active"] >= dogs["customers"]["churned"] + dogs["customers"]["active"]
    assert api().get("/api/customer-profiles/journey", params={"c": "colour:red"}).status_code == 400


def test_those_who_left_faded_out_visiting_and_ordering_less_in_each_month_before_their_last_order():
    """Found in the data, not planted as such: the less engaged are the ones who leave, and visits fall before orders do."""
    cells = api().get("/api/customer-profiles/journey").json()["cells"]

    for code in ("visit", "order"):
        before = [c for c in cells[code] if c["offset"] in (-4, -3, -2, -1)]
        assert all(c["churned"] < c["active"] and c["clear"] for c in before), code
    first = lambda code: next(c["offset"] for c in cells[code] if c["clear"])
    assert first("visit") <= first("order"), "visits fall at least as early as orders"


def test_the_shop_sent_those_who_left_clearly_more_actions_after_their_last_order():
    after = [c for c in api().get("/api/customer-profiles/journey").json()["cells"]["action"] if c["offset"] in (0, 1, 2)]

    assert all(c["churned"] > c["active"] and c["clear"] for c in after)


def test_a_segment_under_the_minimum_gets_its_size_and_no_grid():
    body = api().get("/api/customer-profiles/journey", params={"c": ["pets:aquarium", "price:premium-leaning", "offer:mostly", "rating:above-average ratings"]}).json()

    assert body["too_small"] is True and "cells" not in body


def test_no_row_of_the_journey_names_a_customer():
    import json
    assert "CUST-" not in json.dumps(api().get("/api/customer-profiles/journey").json())
