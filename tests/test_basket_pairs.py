"""Offline tests for Shop analytics' baskets (src/basket_pairs.py), with
the fake client from test_shop_analytics.py."""

from __future__ import annotations

from src.basket_pairs import TOKEN_LIMIT, get_basket_section
from src.basket_rules_service import MINED_ANCHORS
from tests.test_shop_analytics import FakeClient, hit, key


def basket_answer(anchor, *hits):
    return {key("orders", {"line_categories": {"$match": anchor}}, "line_categories"): list(hits)}


def test_baskets_relate_each_anchor_category_over_order_tokens():
    client = FakeClient()

    get_basket_section(client)

    sent = client.sent("orders")
    assert len(sent) == len(MINED_ANCHORS)
    assert all(r["relate"] == "line_categories" and r["limit"] == TOKEN_LIMIT for r in sent)
    assert {"line_categories": {"$match": "dog_dryfood"}} in [r["where"] for r in sent]


def test_each_anchor_gets_its_own_design_effect_from_its_customers():
    client = FakeClient()

    section = get_basket_section(client)

    anchor_wheres = [r["where"] for r in client.relates if r["from"] == "orders" and r["relate"] == "customer_id"]
    assert {"line_categories": {"$match": "cat_litter"}} in anchor_wheres
    assert set(section.design_effects) >= {"Dog dry-food", "Cat litter"}


def test_a_basket_pair_skips_the_anchor_itself_and_is_shown_once():
    self_hit = hit("line_categories", "dog_dryfood", 2.91, 4_100, 4_100, 4_100, 12_000)
    dental = hit("line_categories", "dog_dentaltreats", 2.79, 2_699, 4_100, 2_900, 12_000)
    reverse = hit("line_categories", "dog_dryfood", 2.79, 2_699, 2_900, 4_100, 12_000)
    client = FakeClient({**basket_answer("dog_dryfood", self_hit, dental),
                         **basket_answer("dog_dentaltreats", reverse)})

    section = get_basket_section(client)

    assert [(p.first, p.second, p.lift, p.orders_with_both) for p in section.pairs] == [
        ("Dog dry-food", "Dog dental-treats", 2.79, 2_699),
    ]
    # The reverse pair is not a second test: one test for dry-food + dental,
    # and one neutral pair from each of the other eight anchors.
    assert section.significance.tested == 1 + (len(MINED_ANCHORS) - 2)
