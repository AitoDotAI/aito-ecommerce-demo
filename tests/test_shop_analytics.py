"""Offline tests for Shop analytics' clicks-and-purchases and who/when
sections (src/shop_analytics_service.py) and the rules every section
shares (src/lift_rows.py, src/design_effect.py).

The fake client answers `relate` from a table of hits keyed by (table,
where, field); anything not in the table gets one value at lift 1.0, on
enough rows to be tested. `_relate`s on the customer column answer from
a list of (rows, rows meeting the condition) per customer, which sets the
design effect. Hits are in the shape `normalize_response` produces.
Baskets and search words are in their own test files; the live behaviour
is asserted in `test_aito_check.py`.
"""

from __future__ import annotations

import json

import pytest

from src.aito_client import AitoError
from src.demand_service import season_months
from src.design_effect import design_effect
from src.shop_analytics_service import (FUNNEL_FIELDS, WHO_FIELDS, WINDOW_MONTHS, get_funnel_section,
                                        get_who_section)


def hit(field, value, lift, on_condition, condition=12_000, f=11_000, n=115_000):
    return {"related": {field: {"$has": value}}, "lift": lift,
            "fs": {"fOnCondition": on_condition, "fCondition": condition, "f": f, "n": n}}


def key(table, where, field):
    return table, json.dumps(where, sort_keys=True), field


# 100 customers, 50 rows each, 5 meeting the condition: no clustering.
UNCLUSTERED = [(50, 5)] * 100
CUSTOMER_FIELDS = ("context.customer", "order_id.customer_id", "customer_id")
POPULATIONS = [{"context.month": {"$or": WINDOW_MONTHS}}, {"order_id.month": {"$or": WINDOW_MONTHS}},
               {"month": {"$or": WINDOW_MONTHS}},
               {"context.surface": "search"}]


class FakeClient:
    def __init__(self, answers: dict | None = None, customers=UNCLUSTERED, counts: dict | None = None):
        self.answers = answers or {}
        self.customers = customers
        self.counts = counts or {}
        self.relates: list[dict] = []
        self.searches: list[dict] = []
        self._example = ""

    def relate(self, *, table, where, relate_field, limit):
        self.relates.append({"from": table, "where": where, "relate": relate_field, "limit": limit})
        if relate_field in CUSTOMER_FIELDS:
            return {"hits": self._customer_hits(where, relate_field)}
        hits = self.answers.get(key(table, where, relate_field))
        if hits is None:
            hits = [hit(relate_field, "neutral", 1.0, 1_150)]
        return {"hits": hits}

    def _customer_hits(self, where, field):
        rows = sum(n for n, _ in self.customers)
        population = where in POPULATIONS
        meeting = rows if population else sum(y for _, y in self.customers)
        return [hit(field, f"C{i}", 1.0, n if population else y, meeting, n, rows)
                for i, (n, y) in enumerate(self.customers) if (n if population else y) > 0]

    def search(self, table, *, where, select=None, limit=10):
        if table == "contexts":     # the example search for the phrase counted just before
            return {"total": 1, "hits": [{"search_query": self._example}]}
        self.searches.append(where)
        total, self._example = self.counts[json.dumps(where, sort_keys=True)]
        return {"total": total, "hits": []}

    def sent(self, table: str) -> list[dict]:
        return [r for r in self.relates if r["from"] == table and r["relate"] not in CUSTOMER_FIELDS]


PURCHASED = {"purchased": True}


def funnel_answer(field, *hits):
    return {key("impressions", PURCHASED, field): list(hits)}


# ── The design effect ────────────────────────────────────────────────


def test_no_clustering_gives_a_design_effect_of_1():
    customers = {f"C{i}": 50 for i in range(100)}
    meeting = {f"C{i}": 5 for i in range(100)}

    assert design_effect(customers, meeting).design_effect == 1.0


def test_a_condition_shared_by_all_of_a_customers_rows_gives_the_rows_per_customer():
    # Half the customers meet the condition on every row, half on none:
    # each customer is one observation, so the design effect is m = 20.
    customers = {f"C{i}": 20 for i in range(100)}
    meeting = {f"C{i}": 20 for i in range(50)}

    effect = design_effect(customers, meeting)

    assert (effect.intra_customer_correlation, effect.design_effect) == (1.0, 20.0)


def test_a_customer_meeting_the_condition_outside_the_population_fails_loudly():
    with pytest.raises(AitoError, match="not in the population"):
        design_effect({"C1": 10, "C2": 10}, {"C3": 1})


# ── 1. What goes with a click and a purchase ─────────────────────────


def test_every_funnel_field_is_related_to_purchases_on_impressions():
    client = FakeClient()

    get_funnel_section(client)

    assert sorted(r["relate"] for r in client.sent("impressions")) == sorted(FUNNEL_FIELDS)
    assert all(r["where"] == PURCHASED for r in client.sent("impressions"))


def test_the_clicked_kpi_relates_the_same_fields_to_clicks():
    client = FakeClient()

    section = get_funnel_section(client, kpi="clicked")

    assert all(r["where"] == {"clicked": True} for r in client.sent("impressions"))
    assert section.selected == "clicked"


def test_the_design_effect_is_measured_on_the_customer_column():
    client = FakeClient()

    get_funnel_section(client)

    customer_wheres = [r["where"] for r in client.relates if r["relate"] == "context.customer"]
    assert customer_wheres == [{"context.month": {"$or": WINDOW_MONTHS}}, PURCHASED]


def test_a_lift_whose_interval_excludes_1_is_shown_with_its_counts():
    # 1–2 star products: 923 of 12,135 purchases, against 11,525 of 115,690
    # impressions (the probe on `shoppers`, 2026-10-13).
    low_rated = hit("product_sku.rating_band", "1-2", 0.789, 923, 12_135, 11_525, 115_690)
    section = get_funnel_section(FakeClient(funnel_answer("product_sku.rating_band", low_rated)))

    row = next(r for r in section.rows if r.field == "product_sku.rating_band")
    assert (row.value, row.lift, row.rows_with_value, row.condition_rows) == ("1-2", 0.79, 923, 12_135)
    assert row.interval_low < row.interval_high < 1


def test_clustering_widens_the_interval():
    low_rated = hit("product_sku.rating_band", "1-2", 0.789, 923, 12_135, 11_525, 115_690)
    answers = funnel_answer("product_sku.rating_band", low_rated)
    # Half the customers buy four times as often as the other half.
    clustered = [(50, 8)] * 50 + [(50, 2)] * 50

    plain = get_funnel_section(FakeClient(answers)).rows[0]
    widened = get_funnel_section(FakeClient(answers, customers=clustered))

    assert widened.clustering.design_effect > 1
    assert widened.rows[0].interval_high - widened.rows[0].interval_low > plain.interval_high - plain.interval_low


def test_support_counts_independent_purchases_not_rows():
    # 0.3× on 40 purchases would clear 1 easily, but with a design effect
    # of 2 it rests on 20 independent purchases, under the minimum of 30.
    just_bought = hit("just_bought", True, 0.3, 40, 12_135, 1_271, 115_690)
    clustered = [(50, 8)] * 50 + [(50, 2)] * 50

    section = get_funnel_section(FakeClient(funnel_answer("just_bought", just_bought), customers=clustered))

    assert section.clustering.design_effect == 2.02
    assert section.significance.tested == len(FUNNEL_FIELDS) - 1
    assert "just_bought" in section.fields_without_clear_effect


def test_a_lift_whose_interval_includes_1_is_left_out_and_its_field_has_no_clear_effect():
    # 1.05× on 600 purchases: enough support, but the interval includes 1.
    slight = hit("context.surface", "bought_together", 1.05, 600, 12_000, 5_475, 115_000)

    section = get_funnel_section(FakeClient(funnel_answer("context.surface", slight)))

    assert not [r for r in section.rows if r.field == "context.surface"]
    assert "context.surface" in section.fields_without_clear_effect


def test_a_lift_that_passes_alone_is_left_out_when_many_were_tested():
    # 1.08× on 1,000 purchases clears 1 at z = 1.96 (1.01–1.15), not at the
    # Bonferroni z for the seven lifts this section tests (0.99–1.18).
    borderline = hit("context.customer.diet", "senior", 1.08, 1_000, 12_000, 8_873, 115_000)

    section = get_funnel_section(FakeClient(funnel_answer("context.customer.diet", borderline)))

    assert section.significance.tested == len(FUNNEL_FIELDS)
    assert section.significance.z > 2.5
    assert "context.customer.diet" in section.fields_without_clear_effect


def test_an_interval_is_rounded_outward_and_left_out_if_it_then_touches_1():
    # The interval's top is 0.991: shown to two decimals without making it
    # narrower, it reads 1.00.
    sensitive = hit("context.customer.diet", "sensitive", 0.95, 3_250, 12_135, 32_615, 115_690)

    section = get_funnel_section(FakeClient(funnel_answer("context.customer.diet", sensitive)))

    assert "context.customer.diet" in section.fields_without_clear_effect


def test_a_boolean_field_reads_true_not_python_true():
    just_bought = hit("just_bought", True, 0.48, 400, 12_135, 15_030, 115_690)

    section = get_funnel_section(FakeClient(funnel_answer("just_bought", just_bought)))

    assert next(r for r in section.rows if r.field == "just_bought").value == "true"


def test_an_unknown_kpi_is_refused():
    with pytest.raises(ValueError, match="kpi"):
        get_funnel_section(FakeClient(), kpi="added")


def test_a_window_that_misses_rows_fails_loudly_rather_than_misjudge_clustering():
    client = FakeClient()
    client._customer_hits = lambda where, field: [hit(field, "C1", 1.0, 10, 10, 10, 999)]

    with pytest.raises(AitoError, match="cover 10 of 999"):
        get_funnel_section(client)


# ── 2. Who buys what, and when ───────────────────────────────────────


@pytest.mark.parametrize("who, where", [
    ("summer", {"order_id.month": {"$or": season_months("summer")}}),
    ("small_animal", {"order_id.customer_id.pets": {"$match": "small_animal"}}),
    ("grain-free", {"order_id.customer_id.diet": "grain-free"}),
])
def test_who_and_when_relates_categories_over_that_groups_order_lines(who, where):
    client = FakeClient()

    section = get_who_section(client, who=who)

    sent = client.sent("order_lines")
    assert [r["where"] for r in sent] == [where] * len(WHO_FIELDS)
    assert sorted(r["relate"] for r in sent) == sorted(WHO_FIELDS)
    assert section.selected == who and who in [o["id"] for o in section.options]


def test_summer_shows_health_bought_more():
    health = hit("product_sku.category", "health", 3.99, 375, 6_489, 548, 38_906)
    summer = {"order_id.month": {"$or": season_months("summer")}}

    section = get_who_section(FakeClient({key("order_lines", summer, "product_sku.category"): [health]}))

    assert [(r.value, r.lift) for r in section.rows] == [("health", 3.99)]


def test_an_unknown_who_is_refused():
    with pytest.raises(ValueError, match="who"):
        get_who_section(FakeClient(), who="monsoon")


# ── Errors and the query pane ────────────────────────────────────────


def test_a_relate_with_no_hits_fails_loudly():
    with pytest.raises(AitoError, match="no hits"):
        get_funnel_section(FakeClient(funnel_answer("context.customer.pets")))


def test_a_full_page_of_hits_fails_loudly_because_values_may_be_cut_off():
    many = [hit("context.customer.pets", f"s{i}", 1.0, 100) for i in range(50)]

    with pytest.raises(AitoError, match="full page"):
        get_funnel_section(FakeClient(funnel_answer("context.customer.pets", *many)))


def test_a_hit_without_related_has_fails_loudly():
    odd = {"related": {"context.customer.pets": "dog"}, "lift": 1.5,
           "fs": {"fOnCondition": 900, "fCondition": 12_000, "f": 7_000, "n": 115_000}}

    with pytest.raises(AitoError, match="related.context.customer.pets"):
        get_funnel_section(FakeClient(funnel_answer("context.customer.pets", odd)))


def test_query_pane_shows_one_body_that_was_sent_and_how_many_there_were():
    client = FakeClient()

    section = get_funnel_section(client)

    assert section.example_query["body"] in client.relates
    assert section.queries_sent == len(client.relates)
