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


def test_each_cell_is_the_share_of_customers_with_the_event_that_month_relative_to_their_last_order_for_those_who_left_and_those_who_stayed(monkeypatch):
    monkeypatch.setattr("src.customer_journey.control_month", lambda cid, customer, months: "2026-09")
    customers = {f"L{i}": customer("2026-06", True, "2026-01") for i in range(40)} | {f"S{i}": customer("2026-09", False, "2026-01") for i in range(40)}
    events = {f"L{i}": {"2026-05": {"return": 1}} for i in range(30)} | {f"L{i}": {} for i in range(30, 40)}
    events |= {f"S{i}": {"2026-08": {"return": 1}} for i in range(4)} | {f"S{i}": {} for i in range(4, 40)}

    result = journey(events, customers, list(customers), MONTHS)

    assert result["customers"] == {"churned": 40, "active": 40}
    cell = next(c for c in result["cells"]["return"] if c["offset"] == -1)
    assert cell["churned"] == 0.75 and cell["active"] == 0.1
    assert cell["points"] == pytest.approx(65.0) and cell["clear"] is True


def test_a_month_outside_the_data_is_not_counted_for_the_customer_whose_offset_falls_there():
    customers = {f"S{i}": customer("2026-09", False) for i in range(40)} | {f"L{i}": customer("2026-12", True, "2026-01") for i in range(40)}

    result = journey({c: {} for c in customers}, customers, list(customers), MONTHS)

    after = next(c for c in result["cells"]["order"] if c["offset"] == 1)
    assert after["n_churned"] == 0 and after["churned"] is None and after["clear"] is None, "December is the last month: nobody who left on it has a month after"
    assert after["n_active"] == 40


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


def test_before_their_last_order_those_who_left_look_like_those_who_stayed_in_every_kind_of_event():
    """What the data shows once only the months a customer existed are counted: no early warning in these events. (An earlier reading, that they faded out
    before leaving, was months before the customer joined counted as 'no visit'.)"""
    cells = api().get("/api/customer-profiles/journey").json()["cells"]

    for code, row in cells.items():
        assert not any(c["clear"] for c in row if c["offset"] < 0), f"{code}: a clear difference before the last order"


def test_after_their_last_order_those_who_left_stop_visiting_the_shop():
    cells = {c["offset"]: c for c in api().get("/api/customer-profiles/journey").json()["cells"]["visit"]}

    assert all(cells[o]["clear"] and cells[o]["churned"] < cells[o]["active"] for o in (1, 2))


def test_a_segment_under_the_minimum_gets_its_size_and_no_grid():
    body = api().get("/api/customer-profiles/journey", params={"c": ["pets:aquarium", "price:premium-leaning", "offer:mostly", "rating:above-average ratings"]}).json()

    assert body["too_small"] is True and "cells" not in body


def test_no_row_of_the_journey_names_a_customer():
    import json
    assert "CUST-" not in json.dumps(api().get("/api/customer-profiles/journey").json())


def test_those_who_stayed_are_lined_up_on_an_ordinary_order_they_kept_ordering_after_not_on_their_last_one():
    # Their last order is just the latest in the data: lined up on it, nobody orders in the months after, by definition.
    stayed = {f"S{i}": customer("2026-12", False, "2026-03") for i in range(40)}
    left = {f"L{i}": customer("2026-05", True, "2026-02") for i in range(40)}
    customers = stayed | left
    # the stayed also ordered in 2026-06 and 2026-08, in the three months after their control month
    for c in stayed.values():
        c["months"]["2026-05"] = [1, 10.0, 5.0]

    result = journey({c: {} for c in customers}, customers, list(customers), MONTHS)

    after = next(c for c in result["cells"]["order"] if c["offset"] == 1)
    assert result["customers"] == {"churned": 40, "active": 40}
    assert after["churned"] == 0.0, "after their last order, those who left have no order: by definition"
    assert after["n_active"] > 0, "a control order has months after it to look at"


def test_the_control_order_is_picked_among_orders_with_three_months_of_data_after_them_and_the_same_one_every_time():
    customers = {f"S{i}": customer("2026-12", False, "2026-03") for i in range(40)}
    for c in customers.values():
        c["months"]["2026-07"] = [1, 1.0, 1.0]
    customers |= {f"L{i}": customer("2026-04", True, "2026-02") for i in range(40)}

    first = journey({c: {} for c in customers}, customers, list(customers), MONTHS)
    again = journey({c: {} for c in customers}, customers, list(customers), MONTHS)

    assert first == again
    from src.customer_journey import control_month
    assert control_month("S0", customers["S0"], MONTHS) in {"2026-03", "2026-07"}, "2026-12 has no three months after it"


def test_a_customer_who_stayed_with_no_order_old_enough_to_have_three_months_after_it_has_no_control_and_is_counted_apart():
    customers = {f"S{i}": customer("2026-12", False) for i in range(40)} | {f"L{i}": customer("2026-04", True, "2026-02") for i in range(40)}

    result = journey({c: {} for c in customers}, customers, list(customers), MONTHS)

    assert result["customers"]["active"] == 0 and result["without_control"] == 40


def test_months_before_a_customer_existed_are_not_counted_as_months_without_the_event(monkeypatch):
    monkeypatch.setattr("src.customer_journey.control_month", lambda cid, customer, months: "2026-06")
    # Lined up on a control order early in life, most of the five months before it are before the customer's first order.
    young = {f"S{i}": customer("2026-06", False, "2026-05") | {"months": {"2026-05": [1, 1.0, 1.0], "2026-06": [1, 1.0, 1.0]}} for i in range(40)}
    left = {f"L{i}": customer("2026-08", True, "2026-02") for i in range(40)}
    customers = young | left

    result = journey({c: {} for c in customers}, customers, list(customers), MONTHS)

    before = {c["offset"]: c for c in result["cells"]["visit"]}
    assert before[-1]["n_active"] == 40, "one month before 2026-06 is 2026-05: the customer's first order month"
    assert before[-2]["n_active"] == 0, "two months before is 2026-04: before the customer's first order"
    assert before[-2]["n_churned"] == 40


def test_events_that_need_an_order_are_not_compared_after_the_last_order_because_those_who_left_have_none_by_definition():
    customers = {f"S{i}": customer("2026-03", False, "2026-01") | {"months": {"2026-01": [1, 1.0, 1.0], "2026-03": [1, 1.0, 1.0], "2026-04": [1, 1.0, 1.0]}} for i in range(40)}
    customers |= {f"L{i}": customer("2026-03", True, "2026-01") for i in range(40)}
    events = {c: {"2026-04": {"return": 1}} for c in customers if c.startswith("S")}

    result = journey(events, customers, list(customers), MONTHS)

    for code in ("order", "return", "incident", "low_review", "detractor"):
        after = next(c for c in result["cells"][code] if c["offset"] == 1)
        assert after["by_definition"] is True and after["clear"] is None and after["points"] is None, code
    visit = next(c for c in result["cells"]["visit"] if c["offset"] == 1)
    action = next(c for c in result["cells"]["action"] if c["offset"] == 1)
    assert visit["by_definition"] is False and action["by_definition"] is False, "a visit or an action can follow the last order"
    before = next(c for c in result["cells"]["return"] if c["offset"] == -1)
    assert before["by_definition"] is False
