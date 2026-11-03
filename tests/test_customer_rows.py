"""The raw rows behind a selection (ADR 0055): sales by product, orders, individual feedback. No names, no customer ids."""

import json

import pytest

from src.customer_rows import PAGE_MAX, build_rows, page_of

PRODUCTS = {"SKU-A": {"name": "Dog food 2kg", "brand": "Acme", "category": "dry-food", "pet_type": "dog"},
            "SKU-B": {"name": "Cat toy", "brand": "Acme", "category": "toys", "pet_type": "cat"}}
STATES = {"S1": {"price_eur": 10.0}, "S2": {"price_eur": 4.0}}
ORDERS = [{"order_id": "ORD-1", "customer_id": "C1", "month": "2026-01", "total_eur": 24.0},
          {"order_id": "ORD-2", "customer_id": "C2", "month": "2026-02", "total_eur": 4.0},
          {"order_id": "ORD-3", "customer_id": "C9", "month": "2026-02", "total_eur": 99.0}]
LINES = [{"order_id": "ORD-1", "product_sku": "SKU-A", "qty": 2, "returned": False, "product_state": "S1"},
         {"order_id": "ORD-1", "product_sku": "SKU-B", "qty": 1, "returned": True, "product_state": "S2"},
         {"order_id": "ORD-2", "product_sku": "SKU-A", "qty": 1, "returned": False, "product_state": "S1"},
         {"order_id": "ORD-3", "product_sku": "SKU-A", "qty": 9, "returned": False, "product_state": "S1"}]
REVIEWS = [{"customer_id": "C1", "product_sku": "SKU-A", "rating": 1, "text": "Dog was sick.", "category": "quality", "created_at": "2026-02", "replied": False},
           {"customer_id": "C9", "product_sku": "SKU-A", "rating": 5, "text": "Great.", "category": "praise", "created_at": "2026-02", "replied": False}]
ANSWERS = [{"customer": "C2", "month": "2026-03", "score": 9, "nps_group": "promoter", "wrote_negative_review": False}]


@pytest.fixture
def rows():
    return build_rows({"C1", "C2"}, ORDERS, LINES, STATES, PRODUCTS)


def test_only_the_asked_customers_are_in_the_rows_and_a_kept_line_is_paid_for_and_a_returned_one_is_not(rows):
    assert set(rows["customers"]) == {"C1", "C2"}
    assert rows["customers"]["C1"]["lines"] == [["SKU-A", "2026-01", 2, 0, 20.0], ["SKU-B", "2026-01", 1, 1, 0.0]]


def test_sales_by_product_adds_up_units_returns_revenue_and_buyers_biggest_revenue_first(rows):
    result = page_of(rows, REVIEWS, ANSWERS, ["C1", "C2"], "sales", None, 0, 50)

    assert result["total"] == 2
    assert result["rows"][0] == {"product": "Dog food 2kg", "brand": "Acme", "category": "dry-food", "units": 3, "returned_units": 0, "revenue_eur": 30.0, "customers": 2}
    assert result["rows"][1]["returned_units"] == 1 and result["rows"][1]["revenue_eur"] == 0.0


def test_orders_are_listed_newest_first_with_no_customer_in_them(rows):
    result = page_of(rows, REVIEWS, ANSWERS, ["C1", "C2"], "orders", None, 0, 50)

    assert [r["order"] for r in result["rows"]] == ["ORD-2", "ORD-1"]
    assert all("customer" not in r and "customer_id" not in r for r in result["rows"])
    assert result["rows"][1] == {"order": "ORD-1", "month": "2026-01", "total_eur": 24.0, "lines": 2, "returned_lines": 1}


def test_reviews_and_nps_answers_are_separate_tabs_each_of_the_selected_customers_only_newest_first(rows):
    reviews = page_of(rows, REVIEWS, ANSWERS, ["C1", "C2"], "reviews", None, 0, 50)
    answers = page_of(rows, REVIEWS, ANSWERS, ["C1", "C2"], "nps", None, 0, 50)

    assert reviews["rows"] == [{"month": "2026-02", "product": "Dog food 2kg", "stars": 1, "topic": "quality", "replied": False, "text": "Dog was sick."}]
    assert answers["rows"] == [{"month": "2026-03", "score": 9, "group": "promoter", "also_wrote_a_negative_review": False, "comment": None}]
    assert "Great." not in json.dumps(reviews), "a review by a customer outside the selection is not shown"


def test_a_period_keeps_only_its_months_in_every_tab(rows):
    months = {"2026-02"}

    assert [r["order"] for r in page_of(rows, REVIEWS, ANSWERS, ["C1", "C2"], "orders", months, 0, 50)["rows"]] == ["ORD-2"]
    assert page_of(rows, REVIEWS, ANSWERS, ["C1", "C2"], "sales", months, 0, 50)["rows"][0]["units"] == 1
    assert [r["stars"] for r in page_of(rows, REVIEWS, ANSWERS, ["C1", "C2"], "reviews", months, 0, 50)["rows"]] == [1]


def test_a_page_is_a_slice_and_says_how_many_rows_there_are_in_all(rows):
    second = page_of(rows, REVIEWS, ANSWERS, ["C1", "C2"], "orders", None, 1, 1)

    assert second["total"] == 2 and [r["order"] for r in second["rows"]] == ["ORD-1"]


def test_an_unknown_tab_or_a_page_beyond_the_limit_is_refused(rows):
    with pytest.raises(ValueError, match="tab"):
        page_of(rows, REVIEWS, ANSWERS, ["C1"], "customers", None, 0, 10)
    with pytest.raises(ValueError, match="limit"):
        page_of(rows, REVIEWS, ANSWERS, ["C1"], "orders", None, 0, PAGE_MAX + 1)


def api():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from src.customer_profile_routes import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_the_route_serves_each_tab_for_a_selection_and_no_row_names_a_customer():
    for tab in ("sales", "orders", "reviews", "nps"):
        body = api().get("/api/customer-profiles/rows", params={"tab": tab, "c": "pets:dog", "limit": 100}).json()

        assert body["too_small"] is False and body["total"] > 0 and len(body["rows"]) == min(100, body["total"])
        assert "CUST-" not in json.dumps(body), f"{tab}: a row names a customer"


def test_the_route_keeps_a_period_to_its_months_and_pages_through_the_rows():
    everything = api().get("/api/customer-profiles/rows", params={"tab": "orders", "c": "pets:dog", "limit": 1}).json()["total"]
    period = api().get("/api/customer-profiles/rows", params={"tab": "orders", "c": "pets:dog", "start": "2026-01", "end": "2026-03", "limit": 100}).json()

    assert 0 < period["total"] < everything
    assert {r["month"] for r in period["rows"]} <= {"2026-01", "2026-02", "2026-03"}
    second = api().get("/api/customer-profiles/rows", params={"tab": "orders", "c": "pets:dog", "limit": 5, "offset": 5}).json()
    first = api().get("/api/customer-profiles/rows", params={"tab": "orders", "c": "pets:dog", "limit": 10}).json()
    assert second["rows"] == first["rows"][5:10]


def test_a_selection_under_the_minimum_size_shows_no_rows():
    body = api().get("/api/customer-profiles/rows", params={"tab": "orders", "c": ["pets:aquarium", "price:premium-leaning", "offer:mostly", "rating:above-average ratings"]}).json()

    assert body["too_small"] is True and body["rows"] == [] and body["customers"] < body["min_customers"]


def test_a_bad_tab_or_period_or_page_is_a_400():
    for params in ({"tab": "customers"}, {"start": "2026-03", "end": "2026-01"}, {"limit": 1000}, {"start": "2026-01"}):
        assert api().get("/api/customer-profiles/rows", params=params).status_code == 400, params


def test_every_tab_holds_only_the_selected_segments_data_counted_independently_from_the_fixtures():
    """Sales, orders, reviews and NPS answers of a segment are those of its customers and nobody else's (not the whole shop's)."""
    import json
    from pathlib import Path

    from src.customer_selection import members, parse
    from src.customer_selection_data import facts

    data = Path(__file__).resolve().parent.parent / "data"
    chosen = set(members(facts()["customers"], parse(["pets:dog", "price:mixed"])))
    everyone = set(facts()["customers"])
    orders = [o for o in json.loads((data / "orders.json").read_text()) if o["customer_id"] in chosen]
    order_ids = {o["order_id"] for o in orders}
    lines = [ln for ln in json.loads((data / "order_lines.json").read_text()) if ln["order_id"] in order_ids]
    reviews = [r for r in json.loads((data / "reviews.json").read_text()) if r["customer_id"] in chosen]
    answers = [a for a in json.loads((data / "nps_responses.json").read_text()) if a["customer"] in chosen]

    def total(tab: str, customers: list[str]) -> int:
        params = [("tab", tab), ("limit", 1)] + [("c", c) for c in customers]
        return api().get("/api/customer-profiles/rows", params=params).json()["total"]

    conditions = ["pets:dog", "price:mixed"]
    assert total("orders", conditions) == len(orders)
    assert total("reviews", conditions) == len(reviews)
    assert total("nps", conditions) == len(answers)
    sku_units = {}
    for ln in lines:
        sku_units[ln["product_sku"]] = sku_units.get(ln["product_sku"], 0) + (0 if ln["returned"] else ln["qty"])
    sales = api().get("/api/customer-profiles/rows", params=[("tab", "sales"), ("limit", 100)] + [("c", c) for c in conditions]).json()
    assert sum(r["units"] for r in sales["rows"]) <= sum(sku_units.values())
    assert total("orders", conditions) < total("orders", []), "a segment is not the whole shop"
    assert len(chosen) < len(everyone)
