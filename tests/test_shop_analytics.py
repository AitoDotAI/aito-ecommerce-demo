"""Offline tests for Shop analytics (src/shop_analytics_service.py).

Every section of the view is `_relate`, so the fake client answers only
`relate`, from a table of hits keyed by (table, where, field). Anything
not in the table gets one value at lift 1.0: no effect. The hits are in
the shape `normalize_response` produces (`related.<field>.$has`). The
live behaviour of the same queries is asserted in `test_aito_check.py`.
"""

from __future__ import annotations

import json

import pytest

from src.aito_client import AitoError
from src.demand_service import season_months
from src.shop_analytics_service import FUNNEL_FIELDS, WHO_FIELDS, get_shop_analytics


def _hit(field, value, lift, on_condition, condition=12_000, f=11_000, n=115_000):
    return {"related": {field: {"$has": value}}, "lift": lift,
            "fs": {"fOnCondition": on_condition, "fCondition": condition, "f": f, "n": n}}


def _key(table, where, field):
    return table, json.dumps(where, sort_keys=True), field


class FakeClient:
    def __init__(self, answers: dict | None = None):
        self.answers = answers or {}
        self.relates: list[dict] = []

    def relate(self, *, table, where, relate_field, limit):
        self.relates.append({"from": table, "where": where, "relate": relate_field, "limit": limit})
        hits = self.answers.get(_key(table, where, relate_field))
        if hits is None:
            hits = [_hit(relate_field, "neutral", 1.0, 1_150)]
        return {"hits": hits}

    def sent(self, table: str) -> list[dict]:
        return [r for r in self.relates if r["from"] == table]


PURCHASED = {"purchased": True}
SEARCH, SEARCH_PURCHASED = {"surface": "search"}, {"surface": "search", "purchased": True}


# ── 1. What goes with a click and a purchase ─────────────────────────


def test_every_funnel_field_is_related_to_purchases_on_impressions():
    client = FakeClient()

    get_shop_analytics(client)

    funnel = [r for r in client.sent("impressions") if r["where"] == PURCHASED]
    assert sorted(r["relate"] for r in funnel) == sorted(FUNNEL_FIELDS)


def test_the_clicked_kpi_relates_the_same_fields_to_clicks():
    client = FakeClient()

    result = get_shop_analytics(client, kpi="clicked")

    funnel = [r for r in client.sent("impressions") if r["where"] == {"clicked": True}]
    assert sorted(r["relate"] for r in funnel) == sorted(FUNNEL_FIELDS)
    assert result.kpi == "clicked"


def test_a_lift_whose_interval_excludes_1_is_shown_with_its_counts():
    # 1–2 star products: 923 of 12,135 purchases, against 11,525 of 115,690
    # impressions (the probe on `shoppers`, 2026-10-13).
    low_rated = _hit("product_sku.rating_band", "1-2", 0.789, 923, 12_135, 11_525, 115_690)
    client = FakeClient({_key("impressions", PURCHASED, "product_sku.rating_band"): [low_rated]})

    result = get_shop_analytics(client)

    row = next(r for r in result.funnel_rows if r.field == "product_sku.rating_band")
    assert (row.value, row.lift, row.rows_with_value, row.condition_rows) == ("1-2", 0.79, 923, 12_135)
    assert row.interval_low < row.interval_high < 1


def test_a_lift_whose_interval_includes_1_is_left_out_and_its_field_listed_as_no_effect():
    # 1.4× on 12 purchases: the interval is wide enough to include 1.
    thin = _hit("surface", "bought_together", 1.4, 12, 12_000, 700, 115_000)
    client = FakeClient({_key("impressions", PURCHASED, "surface"): [thin]})

    result = get_shop_analytics(client)

    assert not [r for r in result.funnel_rows if r.field == "surface"]
    assert "surface" in result.funnel_fields_without_effect


def test_a_boolean_field_reads_true_not_python_true():
    just_bought = _hit("just_bought", True, 0.48, 40, 12_135, 1_503, 115_690)
    client = FakeClient({_key("impressions", PURCHASED, "just_bought"): [just_bought]})

    result = get_shop_analytics(client)

    row = next(r for r in result.funnel_rows if r.field == "just_bought")
    assert row.value == "true"


def test_an_unknown_kpi_is_refused():
    with pytest.raises(ValueError, match="kpi"):
        get_shop_analytics(FakeClient(), kpi="added")


# ── 2. Who buys what, and when ───────────────────────────────────────


@pytest.mark.parametrize("who, where", [
    ("summer", {"order_id.month": {"$or": season_months("summer")}}),
    ("small_animal_owner", {"customer_segment": "small_animal_owner"}),
    ("grain-free", {"customer_diet_rule": "grain-free"}),
])
def test_who_and_when_relates_categories_over_that_groups_order_lines(who, where):
    client = FakeClient()

    result = get_shop_analytics(client, who=who)

    sent = client.sent("order_lines")
    assert [r["where"] for r in sent] == [where] * len(WHO_FIELDS)
    assert sorted(r["relate"] for r in sent) == sorted(WHO_FIELDS)
    assert result.who == who


def test_summer_shows_grooming_bought_more():
    grooming = _hit("product_sku.category", "grooming", 3.89, 157, 6_489, 212, 38_906)
    summer = {"order_id.month": {"$or": season_months("summer")}}
    client = FakeClient({_key("order_lines", summer, "product_sku.category"): [grooming]})

    result = get_shop_analytics(client, who="summer")

    assert [(r.value, r.lift) for r in result.who_rows] == [("grooming", 3.89)]


def test_an_unknown_who_is_refused():
    with pytest.raises(ValueError, match="who"):
        get_shop_analytics(FakeClient(), who="monsoon")


# ── 3. Baskets ────────────────────────────────────────────────────────


def _basket_answer(anchor, *hits):
    return {_key("orders", {"line_categories": {"$match": anchor}}, "line_categories"): list(hits)}


def test_baskets_relate_each_anchor_category_over_order_tokens():
    client = FakeClient()

    get_shop_analytics(client)

    sent = client.sent("orders")
    assert sent and all(r["relate"] == "line_categories" for r in sent)
    assert {"line_categories": {"$match": "dog_dryfood"}} in [r["where"] for r in sent]


def test_a_basket_pair_skips_the_anchor_itself_and_is_shown_once():
    self_hit = _hit("line_categories", "dog_dryfood", 2.91, 4_100, 4_100, 4_100, 12_000)
    dental = _hit("line_categories", "dog_dentaltreats", 2.79, 2_699, 4_100, 2_900, 12_000)
    reverse = _hit("line_categories", "dog_dryfood", 2.79, 2_699, 2_900, 4_100, 12_000)
    client = FakeClient({**_basket_answer("dog_dryfood", self_hit, dental),
                         **_basket_answer("dog_dentaltreats", reverse)})

    result = get_shop_analytics(client)

    assert [(p.first, p.second, p.lift, p.orders_with_both) for p in result.basket_pairs] == [
        ("Dog dry-food", "Dog dental-treats", 2.79, 2_699),
    ]


# ── 4. Search words ──────────────────────────────────────────────────


def test_a_search_words_lift_is_against_search_impressions_not_all_impressions():
    # 4,000 of 40,000 search impressions end in a purchase (10 %).
    # "cheese": 70 purchases of 280 impressions (25 %), so 2.5×.
    # "food": 1,600 of 16,000 (10 %), so 1.0×, though Aito's lift against
    # all 115,000 impressions would read about 2.9×.
    bought = [_hit("search_query", "cheese", 4.3, 70, 4_000, 280, 115_000),
              _hit("search_query", "food", 2.9, 1_600, 4_000, 16_000, 115_000)]
    shown = [_hit("search_query", "cheese", 2.9, 280, 40_000, 280, 115_000),
             _hit("search_query", "food", 2.9, 16_000, 40_000, 16_000, 115_000)]
    client = FakeClient({_key("impressions", SEARCH_PURCHASED, "search_query"): bought,
                         _key("impressions", SEARCH, "search_query"): shown})

    words = get_shop_analytics(client).search_words

    assert [(w.word, w.lift, w.purchases, w.impressions) for w in words.rows] == [("cheese", 2.5, 70, 280)]
    assert (words.words_checked, words.search_impressions, words.search_purchases) == (2, 40_000, 4_000)


def test_a_word_bought_from_search_but_never_shown_there_fails_loudly():
    bought = [_hit("search_query", "cheese", 4.3, 70, 4_000, 280, 115_000)]
    shown = [_hit("search_query", "food", 2.9, 16_000, 40_000, 16_000, 115_000)]
    client = FakeClient({_key("impressions", SEARCH_PURCHASED, "search_query"): bought,
                         _key("impressions", SEARCH, "search_query"): shown})

    with pytest.raises(AitoError, match="cheese"):
        get_shop_analytics(client)


# ── Errors and the query pane ────────────────────────────────────────


def test_a_relate_with_no_hits_fails_loudly():
    client = FakeClient({_key("impressions", PURCHASED, "customer_segment"): []})

    with pytest.raises(AitoError, match="no hits"):
        get_shop_analytics(client)


def test_a_full_page_of_hits_fails_loudly_because_values_may_be_cut_off():
    many = [_hit("customer_segment", f"s{i}", 1.0, 100) for i in range(500)]
    client = FakeClient({_key("impressions", PURCHASED, "customer_segment"): many})

    with pytest.raises(AitoError, match="full page"):
        get_shop_analytics(client)


def test_a_hit_without_related_has_fails_loudly():
    odd = {"related": {"customer_segment": "dog_owner"}, "lift": 1.5,
           "fs": {"fOnCondition": 900, "fCondition": 12_000, "f": 7_000, "n": 115_000}}
    client = FakeClient({_key("impressions", PURCHASED, "customer_segment"): [odd]})

    with pytest.raises(AitoError, match="related.customer_segment"):
        get_shop_analytics(client)


def test_query_pane_shows_one_body_that_was_sent_and_how_many_there_were():
    client = FakeClient()

    result = get_shop_analytics(client)

    assert result.last_query["body"] in client.relates
    assert result.last_query["of"] == len(client.relates)


def test_an_interval_that_would_display_as_touching_1_is_left_out():
    # 0.96× on 2,560 of 12,135 purchases: the interval's top is 0.996,
    # which two decimals would show as "1.00".
    budget = _hit("customer_lifestyle", "budget", 0.963, 2_560, 12_135, 25_894, 115_690)
    client = FakeClient({_key("impressions", PURCHASED, "customer_lifestyle"): [budget]})

    result = get_shop_analytics(client)

    assert "customer_lifestyle" in result.funnel_fields_without_effect
