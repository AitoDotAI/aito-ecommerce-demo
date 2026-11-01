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
ANSWERS = [{"customer": "C2", "month": "2026-03", "score": 9, "nps_group": "promoter"}]


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


def test_feedback_is_reviews_and_nps_answers_of_the_selected_customers_only_newest_first(rows):
    result = page_of(rows, REVIEWS, ANSWERS, ["C1", "C2"], "feedback", None, 0, 50)

    assert [(r["kind"], r["month"]) for r in result["rows"]] == [("NPS answer", "2026-03"), ("Review", "2026-02")]
    assert result["rows"][1]["text"] == "Dog was sick." and result["rows"][1]["rating"] == 1
    assert "Great." not in json.dumps(result), "a review by a customer outside the selection is not shown"


def test_a_period_keeps_only_its_months_in_every_tab(rows):
    months = {"2026-02"}

    assert [r["order"] for r in page_of(rows, REVIEWS, ANSWERS, ["C1", "C2"], "orders", months, 0, 50)["rows"]] == ["ORD-2"]
    assert page_of(rows, REVIEWS, ANSWERS, ["C1", "C2"], "sales", months, 0, 50)["rows"][0]["units"] == 1
    assert [r["kind"] for r in page_of(rows, REVIEWS, ANSWERS, ["C1", "C2"], "feedback", months, 0, 50)["rows"]] == ["Review"]


def test_a_page_is_a_slice_and_says_how_many_rows_there_are_in_all(rows):
    second = page_of(rows, REVIEWS, ANSWERS, ["C1", "C2"], "orders", None, 1, 1)

    assert second["total"] == 2 and [r["order"] for r in second["rows"]] == ["ORD-1"]


def test_an_unknown_tab_or_a_page_beyond_the_limit_is_refused(rows):
    with pytest.raises(ValueError, match="tab"):
        page_of(rows, REVIEWS, ANSWERS, ["C1"], "customers", None, 0, 10)
    with pytest.raises(ValueError, match="limit"):
        page_of(rows, REVIEWS, ANSWERS, ["C1"], "orders", None, 0, PAGE_MAX + 1)
