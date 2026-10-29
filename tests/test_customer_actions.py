"""`customer_actions` (ADR 0051): the planted situations are in the generated rows.

Each test compares the outcome after an action with the outcome after no
action in the same slice of customers (a slice is a context the shop can
read), and checks the opposite slice too: an action that works on one kind
of customer must not seem to work on the other.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from data.customer_actions import ACTIONS

DATA = Path(__file__).resolve().parent.parent / "data" / "customer_actions.json"


@pytest.fixture(scope="module")
def rows() -> list[dict]:
    if not DATA.exists():
        pytest.skip("customer_actions.json missing — run `./do generate-fixtures`.")
    return json.loads(DATA.read_text(encoding="utf-8"))


def lift(rows, action, in_slice, outcome):
    """(rate after `action`) ÷ (rate after none), among rows in the slice."""
    rate = lambda a: (lambda s: sum(r[outcome] for r in s) / len(s))([r for r in rows if r["action"] == a and in_slice(r)])
    return rate(action) / rate("none")


def test_every_action_is_taken_in_every_recency_so_none_of_them_is_only_seen_where_it_is_expected(rows):
    for recency in ("0-90d", "90-180d", "180d+"):
        taken = {r["action"] for r in rows if r["recency_bucket"] == recency}
        missing = set(ACTIONS) - taken
        assert not missing, f"{recency}: no row with {missing}"


def test_an_email_works_on_customers_who_answered_one_before_and_not_on_those_who_ignored_them(rows):
    answered = lift(rows, "email", lambda r: r["email_history"] == "responded" and r["open_issue"] == "none", "visited_30d")
    ignored = lift(rows, "email", lambda r: r["email_history"] == "ignored" and r["open_issue"] == "none", "visited_30d")
    assert answered >= 1.25 and ignored <= 1.15, (answered, ignored)


def test_a_discount_works_on_customers_who_mostly_buy_on_offer_and_not_on_those_who_rarely_do(rows):
    mostly = lift(rows, "discount", lambda r: r["offer_buyer"] == "mostly", "purchased_30d")
    rarely = lift(rows, "discount", lambda r: r["offer_buyer"] == "rarely", "purchased_30d")
    assert mostly >= 1.7 and rarely <= 1.3, (mostly, rarely)


def test_a_voucher_brings_back_lapsed_customers_more_than_recent_ones(rows):
    lapsed = lift(rows, "voucher", lambda r: r["recency_bucket"] == "180d+", "visited_30d")
    recent = lift(rows, "voucher", lambda r: r["recency_bucket"] == "0-90d", "visited_30d")
    assert lapsed >= 1.8 and recent <= 1.3, (lapsed, recent)


def test_an_ad_reaches_customers_who_consented_to_tracking_and_not_the_others(rows):
    consented = lift(rows, "ad", lambda r: r["tracking_consent"] == "yes", "visited_30d")
    declined = lift(rows, "ad", lambda r: r["tracking_consent"] == "no", "visited_30d")
    assert consented >= 1.3 and declined <= 1.2, (consented, declined)


def test_an_apology_works_on_an_open_issue_and_is_wasted_on_the_rest(rows):
    with_issue = lift(rows, "apology", lambda r: r["open_issue"] != "none", "purchased_30d")
    without = lift(rows, "apology", lambda r: r["open_issue"] == "none", "visited_30d")
    assert with_issue >= 2.0 and without <= 1.2, (with_issue, without)


def test_the_cost_of_a_discount_or_voucher_is_paid_only_when_the_customer_orders(rows):
    for r in rows:
        if r["action"] in ("discount", "voucher") and not r["purchased_30d"]:
            assert r["cost_eur"] == 0, r
        assert r["net_30d_eur"] == pytest.approx(r["spend_30d_eur"] - r["cost_eur"], abs=0.01), r


def test_an_order_needs_a_click_and_a_click_needs_a_visit(rows):
    for r in rows:
        assert r["visited_30d"] >= r["clicked_30d"] >= r["purchased_30d"] >= r["purchased_7d"], r
