"""Offline tests for Patterns' baskets (src/basket_pairs.py), with the
fake client from test_shop_analytics.py."""

from __future__ import annotations

from src.basket_pairs import MINED_ANCHORS, TOKEN_LIMIT, decode_token, get_basket_section
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


def test_a_basket_pair_reads_as_a_rule_both_ways_from_the_hits_counts():
    # fCondition: orders with dry food; f: orders with dental treats;
    # fOnCondition: orders with both; n: all orders.
    dental = hit("line_categories", "dog_dentaltreats", 2.66, 2_911, 4_325, 3_008, 11_909)
    client = FakeClient(basket_answer("dog_dryfood", dental))

    pair = get_basket_section(client).pairs[0]

    assert (pair.first_id, pair.second_id) == ("dog_dryfood", "dog_dentaltreats")
    assert (pair.orders_with_first, pair.orders_with_second, pair.orders) == (4_325, 3_008, 11_909)
    # Two thirds of dry-food baskets hold dental treats, but nearly every
    # dental-treats basket holds dry food: the rule has a direction.
    assert (pair.confidence, pair.reverse_confidence, pair.support) == (0.673, 0.968, 0.244)


def test_the_anchor_filter_offers_every_mined_anchor_by_its_token():
    section = get_basket_section(FakeClient())

    assert [a["id"] for a in section.anchors][:2] == ["dog_dryfood", "dog_wetfood"]
    assert {"id": "aquarium_aquarium", "label": "Aquarium products"} in section.anchors
    assert len(section.anchors) == len(MINED_ANCHORS)


def test_a_category_token_decodes_on_its_last_underscore():
    assert decode_token("small_animal_dryfood") == ("small_animal", "dry-food")
    assert decode_token("dog_dentaltreats") == ("dog", "dental-treats")
