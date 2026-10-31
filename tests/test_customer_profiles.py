"""Customer profiles (ADR 0053): observed traits, consent-only, thin cells without lifts, and stored files that match the fixtures."""

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.customer_profile_routes import router
from src.customer_profiles import DATA, build
from src.customer_segments import THIN_BELOW, response, segments
from src.customer_traits import (MIN_LINES, NOT_PROFILED, TOO_FEW, Reference, offer_band, price_band, rating_band,
                                 traits_for)

PROFILES = DATA / "customer_profiles"
PRODUCTS = {
    "A": {"sku": "A", "category": "food", "pet_type": "dog", "price_eur": 5.0, "avg_rating": 4.5, "dietary": "grain-free"},
    "B": {"sku": "B", "category": "food", "pet_type": "dog", "price_eur": 9.0, "avg_rating": 3.5, "dietary": None},
}
REF = Reference(median_price={("food", "dog"): 7.0}, mean_rating={("food", "dog"): 4.0})


def line(sku: str, on_offer: bool = False) -> tuple[dict, dict]:
    state = {"on_offer": on_offer, "price_eur": PRODUCTS[sku]["price_eur"], "list_price_eur": PRODUCTS[sku]["price_eur"]}
    return {"product_sku": sku, "product_state": f"{sku}-{on_offer}"}, state


def traits(skus_and_offers: list[tuple[str, bool]], consent: bool = True) -> dict:
    pairs = [line(sku, offer) for sku, offer in skus_and_offers]
    states = {ln["product_state"]: st for ln, st in pairs}
    customer = {"customer_id": "C1", "name": "Test Person", "consent_behavioural": consent, "pets": None}
    return traits_for(customer, [ln for ln, _ in pairs], PRODUCTS, states, REF)


def test_the_bands_cut_where_the_action_table_cuts():
    assert [offer_band(x) for x in (0.0, 0.19, 0.2, 0.39, 0.4, 1.0)] == ["rarely", "rarely", "sometimes", "sometimes", "mostly", "mostly"]
    assert (price_band(0.65), price_band(0.35), price_band(0.5)) == ("value-leaning", "premium-leaning", "mixed")
    assert (rating_band(0.25), rating_band(0.0), rating_band(-0.01)) == ("above-average ratings", "average ratings", "below-average ratings")


def test_a_customer_who_bought_cheap_and_well_rated_on_offer_gets_those_traits():
    result = traits([("A", True), ("A", True), ("A", False)])

    assert (result["offer"], result["price"], result["rating"]) == ("mostly", "value-leaning", "above-average ratings")
    assert result["pets"] == ["dog"] and result["diets"] == ["grain-free"]


def test_a_customer_without_consent_is_not_profiled_at_all():
    result = traits([("A", True)] * 5, consent=False)

    assert result["profiled"] is False
    assert (result["offer"], result["price"], result["rating"], result["pets"], result["diets"]) == (NOT_PROFILED,) * 3 + ([], [])


def test_too_few_purchases_is_said_and_not_guessed():
    result = traits([("A", True)] * (MIN_LINES - 1))

    assert (result["offer"], result["price"], result["rating"]) == (TOO_FEW,) * 3


def test_a_diet_tag_needs_two_lines_of_it():
    assert traits([("A", False), ("B", False), ("B", False)])["diets"] == []
    assert traits([("A", False), ("A", False), ("B", False)])["diets"] == ["grain-free"]


def test_a_profile_holds_only_shopping_and_pet_traits_never_anything_about_the_person():
    allowed = {"customer_id", "name", "lines", "pets_declared", "profiled", "offer", "offer_share", "price", "cheaper_share",
               "rating", "rating_gap", "pets", "diets"}

    assert set(traits([("A", True)] * 4)) <= allowed


def test_the_stored_profiles_are_what_the_fixtures_build_today():
    """Regenerate with ./do customer-profiles when the fixtures change."""
    summary, per_customer = build()

    assert summary == json.loads((PROFILES / "summary.json").read_text())
    assert per_customer == json.loads((PROFILES / "customers.json").read_text())


def test_the_stored_profiles_belong_to_the_release_the_app_serves():
    release = json.loads((DATA / "release-env.json").read_text())["env"]

    assert json.loads((PROFILES / "summary.json").read_text())["release"] == release


def test_exactly_the_customers_who_consented_are_profiled():
    customers = json.loads((DATA / "customers.json").read_text())
    stored = {t["customer_id"]: t for t in json.loads((PROFILES / "customers.json").read_text())}

    assert {cid for cid, t in stored.items() if t["profiled"]} == {c["customer_id"] for c in customers if c["consent_behavioural"]}


def test_segments_count_customers_and_say_when_a_segment_is_thin():
    money = {"gross_profit_12m_eur": 0.0, "net_revenue_eur": 100.0, "gross_profit_eur": 30.0, "profit_eur": 30.0}
    customers = {"C1": {"churned": True, "total_spent_eur": 100.0, "revenue_eur": 100.0, "revenue_12m_eur": 40.0, **money},
                 "C2": {"churned": False, "total_spent_eur": 300.0, "revenue_eur": 300.0, "revenue_12m_eur": 60.0, **money}}
    profiles = [{"customer_id": cid, "profiled": True, "offer": "mostly", "price": "mixed", "rating": "average ratings",
                 "pets": ["dog"], "diets": []} for cid in customers]

    result = segments(profiles, customers)["by_trait"]["offer"][0]

    assert (result["customers"], result["churn_rate"], result["avg_spend_eur"], result["thin"]) == (2, 0.5, 200.0, True)
    assert (result["revenue_eur"], result["revenue_12m_eur"], result["revenue_share"]) == (400.0, 100.0, 1.0)


BY_OFFER = lambda row: [row["offer_buyer"]]


def rows(action: str, ordered: int, total: int, value: str = "yes", cost: float = 0.0) -> list[dict]:
    return [{"offer_buyer": value, "recency_bucket": "0-90d", "email_history": "never_sent", "tracking_consent": "yes",
             "spend_band": "mid", "open_issue": "none", "action": action, "purchased_30d": i < ordered,
             "spend_30d_eur": 50.0 if i < ordered else 0.0, "cost_eur": cost} for i in range(total)]


def test_a_response_lift_is_the_difference_to_no_action_in_points_with_its_margin():
    cell = response(rows("none", 20, 100) + rows("discount", 40, 100), 0.3, BY_OFFER)["yes"]["actions"]["discount"]

    assert cell["lift_points"] == 20.0 and cell["clear"] is True and 0 < cell["margin_points"] < 20


def test_a_lift_inside_its_margin_is_not_called_clear():
    cell = response(rows("none", 20, 100) + rows("email", 24, 100), 0.3, BY_OFFER)["yes"]["actions"]["email"]

    assert cell["lift_points"] == 4.0 and cell["clear"] is False


def test_a_cell_with_few_rows_has_no_lift_at_all():
    cell = response(rows("none", 20, 100) + rows("ad", 5, THIN_BELOW - 1), 0.3, BY_OFFER)["yes"]["actions"]["ad"]

    assert cell["thin"] is True and cell["lift_points"] is None and cell["clear"] is None


def test_the_planted_discount_effect_shows_in_the_orders_of_those_who_buy_on_offer_and_not_in_what_it_earns():
    """A2: a discount lifts the orders of customers who mostly buy on offer. The action costs more than the extra orders earn."""
    stored = json.loads((PROFILES / "summary.json").read_text())["response"]

    mostly = stored["offer:mostly"]["actions"]["discount"]
    rarely = stored["offer:rarely"]["actions"]["discount"]

    assert mostly["lift_points"] > 5 and rarely["lift_points"] < mostly["lift_points"]
    assert not (mostly["profit_clear"] and mostly["profit_lift_eur"] > 0), "a discount does not clearly pay for itself here"


@pytest.fixture
def api():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_the_summary_route_serves_segments_and_responses(api):
    body = api.get("/api/customer-profiles").json()

    assert body["stale"] is False and body["simulated"] is True
    assert {"offer", "price", "rating", "pets", "diets"} <= set(body["by_trait"])


def test_a_lookup_finds_a_customer_and_returns_the_profile_or_the_fact_there_is_none(api):
    stored = json.loads((PROFILES / "customers.json").read_text())
    profiled = next(t for t in stored if t["profiled"])
    unprofiled = next(t for t in stored if not t["profiled"])

    assert api.get("/api/customer-profiles/customers", params={"q": profiled["name"][:6]}).json()["customers"]
    assert api.get(f"/api/customer-profiles/customers/{profiled['customer_id']}").json()["offer"] == profiled["offer"]
    assert api.get(f"/api/customer-profiles/customers/{unprofiled['customer_id']}").json()["profiled"] is False
    assert api.get("/api/customer-profiles/customers/CUST-NOPE").status_code == 404


def test_a_lookup_needs_two_letters(api):
    assert api.get("/api/customer-profiles/customers", params={"q": "a"}).json() == {"customers": []}


from src.customer_relations import MIN_GROUP, preferences, relations, share_difference


def profile(cid: str, offer: str, price: str, pets=("dog",), profiled=True) -> dict:
    return {"customer_id": cid, "profiled": profiled, "offer": offer, "price": price, "rating": "average ratings",
            "pets": list(pets), "diets": []}


def test_a_share_difference_is_in_points_with_a_margin_that_shrinks_with_more_customers():
    small = share_difference(30, 100, 10, 100)
    large = share_difference(300, 1000, 100, 1000)

    assert small[0] == large[0] == 20.0
    assert large[1] < small[1]


def test_a_relation_is_the_difference_in_share_between_those_with_a_trait_and_those_without():
    profiles = ([profile(f"A{i}", "mostly", "value-leaning" if i < 24 else "mixed") for i in range(30)]
                + [profile(f"B{i}", "rarely", "value-leaning" if i < 6 else "mixed") for i in range(30)])

    found = next(r for r in relations(profiles) if r["if"]["value"] == "mostly" and r["then"]["value"] == "value-leaning")

    assert (found["share_with"], found["share_without"], found["points"]) == (0.8, 0.2, 60.0)
    assert found["clear"] is True


def test_no_relation_is_made_from_a_group_smaller_than_the_minimum():
    profiles = [profile(f"A{i}", "mostly", "mixed") for i in range(MIN_GROUP - 1)] + [profile(f"B{i}", "rarely", "mixed") for i in range(60)]

    assert all(r["if"]["value"] != "mostly" for r in relations(profiles))


def test_a_customer_who_is_not_profiled_is_in_no_relation_and_no_preference():
    profiles = [profile(f"A{i}", "mostly", "mixed") for i in range(40)] + [profile(f"B{i}", "rarely", "mixed", profiled=False) for i in range(40)]

    assert relations(profiles) == []


def test_relations_never_pair_a_trait_with_itself_and_leave_diets_out():
    profiles = [profile(f"A{i}", "mostly" if i % 2 else "rarely", "mixed" if i % 3 else "value-leaning") for i in range(120)]

    found = relations(profiles)

    assert found and all(r["if"]["trait"] != r["then"]["trait"] for r in found)
    assert all(r["if"]["trait"] != "diets" and r["then"]["trait"] != "diets" for r in found)


def test_a_preference_compares_a_segment_with_customers_who_buy_for_the_same_pet_only():
    profiles = ([profile(f"D{i}", "mostly", "mixed", pets=("dog",)) for i in range(40)]
                + [profile(f"E{i}", "rarely", "mixed", pets=("dog",)) for i in range(40)]
                + [profile(f"C{i}", "rarely", "mixed", pets=("cat",)) for i in range(40)])
    nothing = {"categories": set(), "brands": set(), "products": set()}
    bought = {p["customer_id"]: {"dog": dict(nothing), "cat": dict(nothing)} for p in profiles}
    for p in profiles[:40]:
        bought[p["customer_id"]]["dog"] = {"categories": {"treats"}, "brands": set(), "products": set()}

    found = preferences(profiles, bought)["offer:mostly|dog"]["categories"][0]

    assert (found["item"], found["share"], found["share_others"], found["clear"]) == ("treats", 1.0, 0.0, True)
    assert all(entry["pet"] in ("dog", "cat") for entry in preferences(profiles, bought).values())


def test_the_stored_profiles_give_profit_per_segment_that_adds_up_to_the_profiled_profit():
    summary = json.loads((PROFILES / "summary.json").read_text())

    for trait in ("offer", "price", "rating"):
        assert abs(sum(s["profit_eur"] for s in summary["by_trait"][trait]) - summary["profiled_profit_eur"]) < 1.0, trait


def test_the_stored_profit_is_the_profit_of_the_fixtures_for_the_profiled_customers():
    from src.customer_profit import profit_by_customer

    orders = {o["order_id"]: o for o in json.loads((DATA / "orders.json").read_text())}
    states = {s["product_state_id"]: s for s in json.loads((DATA / "product_states.json").read_text())}
    cost = {i["sku"]: i["unit_cost_eur"] for i in json.loads((DATA / "inventory.json").read_text())}
    profits = profit_by_customer(json.loads((DATA / "order_lines.json").read_text()), orders, states, cost,
                                 json.loads((DATA / "customer_actions.json").read_text()), "2025-05")
    stored = json.loads((PROFILES / "customers.json").read_text())
    summary = json.loads((PROFILES / "summary.json").read_text())

    assert round(sum(profits.get(t["customer_id"], {"profit_eur": 0.0})["profit_eur"] for t in stored if t["profiled"]), 2) == summary["profiled_profit_eur"]


def test_the_stored_profiles_give_revenue_per_segment_that_adds_up_to_the_profiled_revenue():
    summary = json.loads((PROFILES / "summary.json").read_text())

    for trait in ("offer", "price", "rating"):
        total = sum(s["revenue_eur"] for s in summary["by_trait"][trait])
        assert abs(total - summary["profiled_revenue_eur"]) < 1.0, trait


def test_revenue_is_the_sum_of_the_orders_of_the_profiled_customers():
    orders = json.loads((DATA / "orders.json").read_text())
    stored = {t["customer_id"] for t in json.loads((PROFILES / "customers.json").read_text()) if t["profiled"]}
    summary = json.loads((PROFILES / "summary.json").read_text())

    assert round(sum(o["total_eur"] for o in orders if o["customer_id"] in stored), 2) == summary["profiled_revenue_eur"]


# ── Review of #139: the price trait is not made by discounts, scope, margins, consent ──


def test_a_discounted_line_is_not_a_cheaper_choice_just_because_it_is_discounted():
    """The trait asks what the customer chose, not what they paid: a state's list price is compared, so an offer cannot make it."""
    products = {"B": {"sku": "B", "category": "food", "pet_type": "dog", "price_eur": 9.0, "avg_rating": 4.0, "dietary": None}}
    ref = Reference(median_price={("food", "dog"): 7.0}, mean_rating={("food", "dog"): 4.0})
    states = {f"B-{i}": {"on_offer": True, "price_eur": 5.0, "list_price_eur": 9.0} for i in range(4)}
    lines = [{"product_sku": "B", "product_state": f"B-{i}"} for i in range(4)]
    customer = {"customer_id": "C1", "name": "T", "consent_behavioural": True}

    result = traits_for(customer, lines, products, states, ref)

    assert result["offer"] == "mostly" and result["cheaper_share"] == 0.0 and result["price"] == "premium-leaning"


def test_the_reference_median_is_over_list_prices_so_both_sides_of_the_comparison_ignore_offers():
    from src.customer_traits import reference_for

    products = [{"sku": "A", "category": "food", "pet_type": "dog"}, {"sku": "B", "category": "food", "pet_type": "dog"},
                {"sku": "C", "category": "food", "pet_type": "dog"}]
    states = [{"product_sku": "A", "list_price_eur": 4.0, "price_eur": 1.0}, {"product_sku": "B", "list_price_eur": 6.0, "price_eur": 6.0},
              {"product_sku": "C", "list_price_eur": 10.0, "price_eur": 10.0}]

    assert reference_for(products, states).median_price[("food", "dog")] == 6.0


def test_a_difference_inside_its_margin_is_not_clear_in_a_relation():
    profiles = ([profile(f"A{i}", "mostly", "value-leaning" if i < 16 else "mixed") for i in range(30)]
                + [profile(f"B{i}", "rarely", "value-leaning" if i < 13 else "mixed") for i in range(30)])

    found = next(r for r in relations(profiles) if r["if"]["value"] == "mostly" and r["then"]["value"] == "value-leaning")

    assert found["points"] == 10.0 and found["clear"] is False


def test_a_difference_inside_its_margin_is_not_clear_in_a_preference():
    profiles = ([profile(f"D{i}", "mostly", "mixed") for i in range(40)] + [profile(f"E{i}", "rarely", "mixed") for i in range(40)])
    bought = {p["customer_id"]: {"dog": {"categories": set(), "brands": set(), "products": set()}, "cat": {"categories": set(), "brands": set(), "products": set()}} for p in profiles}
    for p in profiles[:40]:
        bought[p["customer_id"]]["dog"]["categories"] = {"treats"}
    for p in profiles[40:]:
        bought[p["customer_id"]]["dog"]["categories"] = {"treats"} if int(p["customer_id"][1:]) < 36 else set()

    row = preferences(profiles, bought)["offer:mostly|dog"]["categories"][0]

    assert row["points"] == 10.0 and row["clear"] is False


def test_the_lookup_gives_no_name_and_no_profile_data_for_a_customer_who_did_not_consent(api):
    stored = json.loads((PROFILES / "customers.json").read_text())
    unprofiled = next(t for t in stored if not t["profiled"])

    body = api.get(f"/api/customer-profiles/customers/{unprofiled['customer_id']}").json()

    assert body["profiled"] is False
    assert not ({"name", "lines", "pets_declared", "pets"} & set(body))
    found = api.get("/api/customer-profiles/customers", params={"q": unprofiled["name"]}).json()["customers"]
    assert unprofiled["customer_id"] not in {c["customer_id"] for c in found}
    assert api.get("/api/customer-profiles/customers", params={"q": unprofiled["customer_id"]}).json()["customers"] == []


def test_a_request_that_names_a_sandbox_is_told_the_profiles_are_the_release_data(api):
    plain = api.get("/api/customer-profiles").json()
    sandboxed = api.get("/api/customer-profiles", params={"db": "tmp-abc"}).json()

    assert plain["scope"] == "release" and sandboxed["scope"] == "release-not-sandbox"


# ── Profit (ADR 0053): what a customer earned the shop ──

from src.customer_profit import distribution, gross_margin, profit_by_customer


def _profit_inputs():
    orders = {"O1": {"customer_id": "C1", "month": "2026-01"}, "O2": {"customer_id": "C1", "month": "2024-01"}}
    states = {"S1": {"price_eur": 10.0}, "S2": {"price_eur": 8.0}}
    cost = {"A": 6.0, "B": 5.0}
    lines = [{"order_id": "O1", "product_sku": "A", "product_state": "S1", "qty": 2, "returned": False},
             {"order_id": "O2", "product_sku": "B", "product_state": "S2", "qty": 1, "returned": False},
             {"order_id": "O1", "product_sku": "A", "product_state": "S1", "qty": 1, "returned": True}]
    return lines, orders, states, cost


def test_profit_is_the_price_paid_less_the_unit_cost_per_line_kept_less_the_action_costs():
    lines, orders, states, cost = _profit_inputs()

    result = profit_by_customer(lines, orders, states, cost, [{"customer_id": "C1", "cost_eur": 1.5}], "2025-05")["C1"]

    assert result["net_revenue_eur"] == 28.0           # 2 x 10 + 1 x 8; the returned line earns nothing
    assert result["gross_profit_eur"] == 11.0          # (10 - 6) x 2 + (8 - 5)
    assert result["gross_profit_12m_eur"] == 8.0       # only the 2026 order is in the last 12 months
    assert result["profit_eur"] == 9.5 and result["returned_lines"] == 1


def test_an_offer_lowers_profit_because_the_price_paid_is_what_counts():
    lines, orders, _, cost = _profit_inputs()

    full = profit_by_customer(lines, orders, {"S1": {"price_eur": 10.0}, "S2": {"price_eur": 8.0}}, cost, [], "2025-05")["C1"]
    offer = profit_by_customer(lines, orders, {"S1": {"price_eur": 8.0}, "S2": {"price_eur": 8.0}}, cost, [], "2025-05")["C1"]

    assert full["profit_eur"] - offer["profit_eur"] == 4.0


def test_the_gross_margin_is_profit_over_the_price_paid_for_the_lines_kept():
    lines, orders, states, cost = _profit_inputs()

    assert round(gross_margin(profit_by_customer(lines, orders, states, cost, [], "2025-05")), 4) == round(11.0 / 28.0, 4)


def test_the_distribution_names_the_median_the_top_tenths_share_and_who_loses_money():
    by_customer = {f"C{i}": {"profit_eur": float(v)} for i, v in enumerate([-5, 10, 10, 10, 10, 10, 10, 10, 10, 100])}

    found = distribution(by_customer, list(by_customer))

    assert found["median_eur"] == 10.0 and found["losing_money"] == 1 and found["top_tenth_share"] == round(100 / 175, 3)


def test_an_action_that_costs_more_than_it_brings_has_a_negative_clear_profit_lift():
    costly = rows("discount", 40, 200, cost=4.0)       # 20 % order at 50 spend, margin 0.3: 3.0 earned per row less 4.0 cost
    cheap = rows("none", 40, 200)

    cell = response(costly + cheap, 0.3, BY_OFFER)["yes"]["actions"]["discount"]

    assert cell["profit_lift_eur"] == -4.0 and cell["profit_clear"] is True


def test_a_profit_lift_inside_its_margin_is_not_clear_and_a_thin_cell_has_none():
    lifted = response(rows("email", 41, 200) + rows("none", 40, 200), 0.3, BY_OFFER)["yes"]["actions"]["email"]
    thin = response(rows("ad", 5, THIN_BELOW - 1) + rows("none", 40, 200), 0.3, BY_OFFER)["yes"]["actions"]["ad"]

    assert lifted["profit_clear"] is False
    assert thin["profit_lift_eur"] is None and thin["profit_clear"] is None
