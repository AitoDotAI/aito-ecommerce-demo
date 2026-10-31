"""A selection of conditions (ADR 0053, the topic tree): customers who meet all of them, counted from the stored facts."""

import pytest

from src.customer_selection import MIN_GROUP, key_of, members, options, parse, view
from src.customer_selection_data import actions, answers, facts, reviews, summary


def customer(**own) -> dict:
    return {"offer": "mostly", "price": "mixed", "rating": "average ratings", "margin": "high-margin", "pets": ["dog"], "diets": [],
            "churned": False, "total_spent_eur": 10.0, "net_revenue_eur": 10.0, "gross_profit_eur": 3.0, "gross_profit_12m_eur": 3.0,
            "profit_eur": 3.0, "funnel": [4, 3, 2, 1], "first": None, "months": {},
            "bought": {"dog": {"categories": [], "brands": [], "products": []}, "cat": {"categories": [], "brands": [], "products": []}}, **own}


def test_a_customer_has_one_value_of_a_shopping_trait_so_two_of_one_is_refused():
    with pytest.raises(ValueError, match="one value of each"):
        parse(["price:mixed", "price:value-leaning"])


def test_pets_can_be_ticked_twice_because_a_customer_can_buy_for_both():
    assert parse(["pets:dog", "pets:cat"]) == [("pets", "cat"), ("pets", "dog")]


def test_a_condition_that_is_not_a_trait_and_a_value_is_refused():
    for bad in ("dog", "colour:red", "offer:"):
        with pytest.raises(ValueError, match="Not a condition"):
            parse([bad])


def test_the_key_is_the_conditions_in_a_fixed_order_and_all_when_there_are_none():
    assert key_of(parse(["pets:dog", "offer:mostly"])) == "offer:mostly+pets:dog"
    assert key_of(parse([])) == "all"


def test_a_selection_is_the_customers_who_meet_every_condition():
    customers = {"A": customer(pets=["dog", "cat"]), "B": customer(pets=["dog"]), "C": customer(price="value-leaning", pets=["cat"])}

    assert members(customers, parse(["pets:dog", "pets:cat"])) == ["A"]
    assert members(customers, parse(["price:mixed", "pets:dog"])) == ["A", "B"]


def test_the_tree_counts_what_a_condition_would_leave_and_a_value_replaces_the_traits_other_value():
    customers = {"A": customer(), "B": customer(price="value-leaning"), "C": customer(price="value-leaning", pets=["cat"])}

    counts = options(customers, parse(["price:mixed"]))

    assert counts["price:value-leaning"] == 2, "ticking another price replaces the first: it is counted on its own"
    assert counts["pets:cat"] == 0, "no customer is mixed-price and has a cat"
    assert counts["pets:dog"] == 1


def test_a_selection_under_the_minimum_is_given_its_size_and_nothing_else():
    small = {"customers": {f"C{i}": customer() for i in range(MIN_GROUP - 1)}, "shares": {}}

    result = view(small, parse(["offer:mostly"]), [], [], [], {})

    assert result["too_small"] is True and result["customers"] == MIN_GROUP - 1
    assert set(result) == {"key", "conditions", "customers", "options", "too_small", "min_customers"}


@pytest.fixture(scope="module")
def release():
    return facts(), summary(), actions(), reviews(), answers()


def test_one_condition_says_what_its_segment_says(release):
    facts, summary, actions, reviews, answers = release

    result = view(facts, parse(["offer:mostly"]), actions, reviews, answers, summary)

    stored_segment = next(s for s in summary["by_trait"]["offer"] if s["value"] == "mostly")
    assert result["segment"]["customers"] == stored_segment["customers"]
    assert result["segment"]["profit_per_customer_eur"] == stored_segment["profit_per_customer_eur"]


def test_premium_dog_owners_are_exactly_the_customers_with_both_traits(release):
    facts, summary, actions, reviews, answers = release
    conditions = parse(["price:premium-leaning", "pets:dog"])

    result = view(facts, conditions, actions, reviews, answers, summary)

    expected = [c for c in facts["customers"].values() if c["price"] == "premium-leaning" and "dog" in c["pets"]]
    assert result["customers"] == len(expected) and result["too_small"] is False
    assert result["funnel"]["selected"]["impressions"] == sum(c["funnel"][0] for c in expected)


def test_every_funnel_step_is_no_wider_than_the_one_before(release):
    facts, summary, actions, reviews, answers = release

    for conditions in ([], ["offer:mostly"], ["price:premium-leaning", "pets:dog"]):
        f = view(facts, parse(conditions), actions, reviews, answers, summary)["funnel"]["selected"]
        assert f["impressions"] >= f["clicks"] >= f["carts"] >= f["purchases"], conditions


def test_nothing_ticked_is_the_whole_profiled_customer_base(release):
    facts, summary, actions, reviews, answers = release

    result = view(facts, parse([]), actions, reviews, answers, summary)

    assert result["key"] == "all" and result["customers"] == summary["profiled"]


def test_the_trend_has_a_zero_for_a_month_the_selection_did_not_order_in():
    own = {f"C{i}": customer(months={"2026-01": [1, 10.0]}) for i in range(MIN_GROUP)}
    stored = {"customers": own | {"X": customer(price="value-leaning", months={"2026-02": [1, 5.0]})},
              "shares": {"cheaper": {cid: 0.1 * (i % 5) + 0.1 for i, cid in enumerate(own | {"X": None})}}, "product_names": {}}

    result = view(stored, parse(["price:mixed"]), [], [], [], {"profiled": 31, "profiled_revenue_eur": 1.0, "profiled_profit_eur": 1.0, "gross_margin": 0.3})

    assert result["trend"]["selected"]["months"] == ["2026-01", "2026-02"]
    assert result["trend"]["selected"]["orders"] == [MIN_GROUP, 0]
    assert result["trend"]["all"]["orders"] == [MIN_GROUP, 1]


def test_the_segment_route_answers_any_combination_and_says_when_it_is_not_one(release):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from src.customer_profile_routes import router

    app = FastAPI()
    app.include_router(router)
    api = TestClient(app)

    both = api.get("/api/customer-profiles/segment", params=[("c", "pets:dog"), ("c", "price:premium-leaning")]).json()
    assert both["key"] == "pets:dog+price:premium-leaning" and both["stale"] is False
    assert api.get("/api/customer-profiles/segment").json()["customers"] == release[1]["profiled"]
    refused = api.get("/api/customer-profiles/segment", params=[("c", "price:mixed"), ("c", "price:value-leaning")])
    assert refused.status_code == 400 and "one value of each" in refused.json()["error"]
