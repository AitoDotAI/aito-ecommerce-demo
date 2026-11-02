"""What a period changed, when no segment is ticked (ADR 0060): what customers bought, and which segments moved, against the period before."""

import pytest

from src.customer_period_mix import preference_changes, segment_changes

MONTHS = ["2026-01", "2026-02", "2026-03", "2026-04"]
PRODUCTS = {"S-1": {"category": "dry-food", "brand": "Acana"}, "S-2": {"category": "toys", "brand": "Kong"}}


def buyers(sku_by_month: dict[str, str], count: int, first: int = 0) -> dict[str, dict]:
    """`count` customers who each bought, in each month, one line of the sku named for that month."""
    return {f"C-{first + i}": {"lines": [[sku, month, 1, 0, 10.0] for month, sku in sku_by_month.items()]} for i in range(count)}


def test_a_category_bought_by_more_customers_in_the_period_than_before_is_reported_as_a_clear_rise():
    # Arrange: 100 customers who bought food before the period and toys in it.
    rows = buyers({"2026-01": "S-1", "2026-02": "S-1", "2026-03": "S-2", "2026-04": "S-2"}, 100)

    changes = preference_changes(rows, PRODUCTS, list(rows), MONTHS, "2026-03", "2026-04")

    toys = next(c for c in changes if c["label"] == "toys")
    assert toys["points"] == 100 and toys["share"] == 1.0 and toys["share_others"] == 0.0
    assert toys["clear"] is True
    food = next(c for c in changes if c["label"] == "dry-food")
    assert food["points"] == -100


def test_when_everyone_buys_more_in_the_period_the_mix_is_what_changes_not_every_item():
    # Twice the lines in the period, in the same proportions: no category has gained a share.
    rows = {f"C-{i}": {"lines": [["S-1", "2026-02", 1, 0, 1.0], ["S-2", "2026-02", 1, 0, 1.0]]
                       + [["S-1", "2026-03", 1, 0, 1.0], ["S-2", "2026-03", 1, 0, 1.0]] * 2} for i in range(30)}

    changes = preference_changes(rows, PRODUCTS, list(rows), MONTHS, "2026-03", "2026-03")

    assert {c["points"] for c in changes} == {0.0}


def test_a_change_inside_the_margin_is_not_called_clear():
    # 20 customers; 10 bought toys before the period, 11 in it: one purchase is luck.
    rows = {f"C-{i}": {"lines": [["S-2" if i < 10 else "S-1", "2026-02", 1, 0, 10.0], ["S-2" if i < 11 else "S-1", "2026-03", 1, 0, 10.0]]}
            for i in range(20)}

    changes = preference_changes(rows, PRODUCTS, list(rows), MONTHS, "2026-03", "2026-03")

    toys = next(c for c in changes if c["label"] == "toys")
    assert toys["points"] == 5.0 and toys["clear"] is False


def test_returned_lines_are_not_something_bought():
    rows = {"C-0": {"lines": [["S-1", "2026-02", 1, 1, 0.0], ["S-2", "2026-02", 1, 0, 10.0], ["S-2", "2026-03", 1, 0, 10.0]]}}

    changes = preference_changes(rows, PRODUCTS, ["C-0"], MONTHS, "2026-03", "2026-03", min_units=1)

    assert {c["label"] for c in changes if c["kind"] == "Category"} == {"toys"}


def test_a_period_with_no_room_before_it_is_refused_not_shortened():
    from src.customer_period import NoPreviousPeriod

    rows = buyers({"2026-01": "S-1"}, 3)
    with pytest.raises(NoPreviousPeriod):
        preference_changes(rows, PRODUCTS, list(rows), MONTHS, "2026-01", "2026-02")


def customer(region: str, spent_before: float, spent_in: float) -> dict:
    return {"region": region, "months": {"2026-02": [1, spent_before, 1.0], "2026-03": [1, spent_in, 1.0]}, "nps": []}


def test_a_segment_that_grew_more_than_the_customers_outside_it_is_clear_and_its_gap_is_stated():
    customers = {f"A-{i}": customer("helsinki", 10.0, 30.0 + i % 3) for i in range(40)}
    customers |= {f"B-{i}": customer("turku", 10.0, 12.0 + i % 3) for i in range(40)}

    moved = segment_changes(customers, MONTHS, "2026-03", "2026-03", ["region:helsinki", "region:turku"], min_customers=30)

    helsinki = next(m for m in moved if m["value"] == "helsinki")
    turku = next(m for m in moved if m["value"] == "turku")
    assert helsinki["clear"] is True and helsinki["gap_eur"] > 15 and helsinki["customers"] == 40 and helsinki["change"] > 1.0
    assert turku["gap_eur"] < -15, "the other segment is the one that lagged"


def test_when_the_whole_shop_grows_alike_no_segment_stands_out():
    customers = {f"A-{i}": customer("helsinki" if i % 2 else "turku", 10.0, 20.0 + i % 3) for i in range(80)}

    moved = segment_changes(customers, MONTHS, "2026-03", "2026-03", ["region:helsinki", "region:turku"], min_customers=30)

    assert moved and not any(m["clear"] for m in moved)


def test_a_segment_below_the_minimum_is_not_listed():
    customers = {f"A-{i}": customer("helsinki", 10.0, 20.0) for i in range(5)}
    customers |= {f"B-{i}": customer("turku", 10.0, 20.0) for i in range(60)}

    moved = segment_changes(customers, MONTHS, "2026-03", "2026-03", ["region:helsinki", "region:turku"], min_customers=30)

    assert moved == [], "helsinki is too small, and turku has too few customers outside it to compare with"
