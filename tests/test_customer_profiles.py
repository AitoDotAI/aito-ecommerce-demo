"""Customer profiles (ADR 0053): observed traits, consent-only, thin cells without lifts, and stored files that match the fixtures."""

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.customer_profile_routes import router
from src.customer_profiles import DATA, build
from src.customer_selection import parse, view
from src.customer_selection_data import actions, answers, facts, reviews, summary
from src.customer_profit import margin_bands
from src.customer_segments import THIN_BELOW, response, segment_keys, segments
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
               "rating", "rating_gap", "pets", "diets", "margin"}

    assert set(traits([("A", True)] * 4)) <= allowed


def test_the_stored_profiles_are_what_the_fixtures_build_today():
    """Regenerate with ./do customer-profiles when the fixtures change."""
    summary, per_customer, per_customer_facts = build()

    assert summary == json.loads((PROFILES / "summary.json").read_text())
    assert per_customer == json.loads((PROFILES / "customers.json").read_text())
    assert per_customer_facts == json.loads((PROFILES / "facts.json").read_text())


def test_the_facts_hold_exactly_the_consenting_customers_and_no_name():
    stored = {t["customer_id"]: t for t in json.loads((PROFILES / "customers.json").read_text())}
    kept = facts()

    assert set(kept["customers"]) == {cid for cid, t in stored.items() if t["profiled"]}
    assert not any("name" in c or "customer_id" in c for c in kept["customers"].values())
    assert all(set(shares) <= set(kept["customers"]) for shares in kept["shares"].values())


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
    profiles = [{"customer_id": cid, "profiled": True, "offer": "mostly", "price": "mixed", "rating": "average ratings", "margin": "high-margin",
                 "pets": ["dog"], "diets": []} for cid in customers]

    result = segments(profiles, customers)["by_trait"]["offer"][0]

    assert (result["customers"], result["churn_rate"], result["avg_spend_eur"], result["thin"]) == (2, 0.5, 200.0, True)
    assert (result["revenue_eur"], result["revenue_share"]) == (200.0, 1.0)


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


def chosen(conditions: list[str]) -> dict:
    """What the view says about a selection, counted from the stored files."""
    return view(facts(), parse(conditions), actions(), reviews(), answers(), summary())


def test_the_planted_discount_effect_shows_in_the_orders_of_those_who_buy_on_offer_and_not_in_what_it_earns():
    """A2: a discount lifts the orders of customers who mostly buy on offer. The action costs more than the extra orders earn."""
    mostly = chosen(["offer:mostly"])["response"]["actions"]["discount"]
    rarely = chosen(["offer:rarely"])["response"]["actions"]["discount"]

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


from src.customer_relations import MIN_GROUP, memberships, selection_preferences, selection_relations, share_difference


def profile(cid: str, offer: str, price: str, pets=("dog",), profiled=True) -> dict:
    return {"customer_id": cid, "profiled": profiled, "offer": offer, "price": price, "rating": "average ratings", "margin": "high-margin",
            "pets": list(pets), "diets": []}


def test_a_share_difference_is_in_points_with_a_margin_that_shrinks_with_more_customers():
    small = share_difference(30, 100, 10, 100)
    large = share_difference(300, 1000, 100, 1000)

    assert small[0] == large[0] == 20.0
    assert large[1] < small[1]


def members_of(profiles: list[dict]) -> dict[str, set]:
    return {p["customer_id"]: memberships(p) for p in profiles if p["profiled"]}


def test_a_relation_is_the_difference_in_share_between_those_selected_and_the_rest():
    profiles = ([profile(f"A{i}", "mostly", "value-leaning" if i < 24 else "mixed") for i in range(30)]
                + [profile(f"B{i}", "rarely", "value-leaning" if i < 6 else "mixed") for i in range(30)])
    selected = {f"A{i}" for i in range(30)}

    found = next(r for r in selection_relations(members_of(profiles), selected, {"offer"}) if r["then"]["value"] == "value-leaning")

    assert (found["share_with"], found["share_without"], found["points"]) == (0.8, 0.2, 60.0)
    assert found["clear"] is True


def test_no_relation_is_made_from_a_selection_smaller_than_the_minimum():
    profiles = [profile(f"A{i}", "mostly", "mixed") for i in range(MIN_GROUP - 1)] + [profile(f"B{i}", "rarely", "mixed") for i in range(60)]

    assert selection_relations(members_of(profiles), {f"A{i}" for i in range(MIN_GROUP - 1)}, {"offer"}) == []


def test_a_customer_who_is_not_profiled_is_in_no_relation():
    profiles = [profile(f"A{i}", "mostly", "mixed") for i in range(40)] + [profile(f"B{i}", "rarely", "mixed", profiled=False) for i in range(40)]

    assert selection_relations(members_of(profiles), {f"A{i}" for i in range(40)}, {"offer"}) == []


def test_relations_leave_out_the_traits_the_selection_is_made_of_and_the_diets():
    profiles = [profile(f"A{i}", "mostly" if i % 2 else "rarely", "mixed" if i % 3 else "value-leaning") for i in range(120)]

    found = selection_relations(members_of(profiles), {p["customer_id"] for p in profiles if p["offer"] == "mostly"}, {"offer"})

    assert found and all(r["then"]["trait"] not in ("offer", "diets") for r in found)


def test_a_preference_compares_a_selection_with_customers_who_buy_for_the_same_pet_only():
    profiles = ([profile(f"D{i}", "mostly", "mixed", pets=("dog",)) for i in range(40)]
                + [profile(f"E{i}", "rarely", "mixed", pets=("dog",)) for i in range(40)]
                + [profile(f"C{i}", "rarely", "mixed", pets=("cat",)) for i in range(40)])
    nothing = {"categories": [], "brands": [], "products": []}
    bought = {p["customer_id"]: {"dog": dict(nothing), "cat": dict(nothing)} for p in profiles}
    for p in profiles[:40]:
        bought[p["customer_id"]]["dog"] = {"categories": ["treats"], "brands": [], "products": []}
    pets_of = {p["customer_id"]: set(p["pets"]) for p in profiles}

    found = selection_preferences({p["customer_id"] for p in profiles[:40]}, pets_of, bought)

    top = found["dog"]["categories"][0]
    assert (top["item"], top["share"], top["share_others"], top["clear"]) == ("treats", 1.0, 0.0, True)
    assert "cat" not in found, "no cat owner is selected, so there is nothing to compare for cats"


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


def test_revenue_is_the_price_paid_on_the_lines_kept_by_the_profiled_customers_the_basis_profit_uses():
    from src.customer_profit import profit_by_customer

    orders = {o["order_id"]: o for o in json.loads((DATA / "orders.json").read_text())}
    states = {st["product_state_id"]: st for st in json.loads((DATA / "product_states.json").read_text())}
    cost = {i["sku"]: i["unit_cost_eur"] for i in json.loads((DATA / "inventory.json").read_text())}
    profits = profit_by_customer(json.loads((DATA / "order_lines.json").read_text()), orders, states, cost, [], "2025-05")
    stored = {t["customer_id"] for t in json.loads((PROFILES / "customers.json").read_text()) if t["profiled"]}
    summary = json.loads((PROFILES / "summary.json").read_text())

    assert round(sum(profits[c]["net_revenue_eur"] for c in stored if c in profits), 2) == summary["profiled_revenue_eur"]


def test_the_stored_totals_are_these_numbers():
    """Literal values: a change in how revenue or profit is counted fails here. Regenerate and read them in when the fixtures change."""
    summary = json.loads((PROFILES / "summary.json").read_text())

    assert (summary["profiled"], summary["profiled_revenue_eur"], summary["profiled_profit_eur"], summary["gross_margin"]) == (
        1790, 467332.96, 139913.04, 0.303)


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
    profiles = ([profile(f"A{i}", "mostly", "value-leaning" if i < 12 else "mixed") for i in range(40)]
                + [profile(f"B{i}", "rarely", "value-leaning" if i < 8 else "mixed") for i in range(40)])

    found = next(r for r in selection_relations(members_of(profiles), {f"A{i}" for i in range(40)}, {"offer"}) if r["then"]["value"] == "value-leaning")

    assert found["points"] == 10.0 and found["clear"] is False


def test_a_difference_inside_its_margin_is_not_clear_in_a_preference():
    profiles = ([profile(f"D{i}", "mostly", "mixed") for i in range(40)] + [profile(f"E{i}", "rarely", "mixed") for i in range(40)])
    bought = {p["customer_id"]: {"dog": {"categories": [], "brands": [], "products": []}, "cat": {"categories": [], "brands": [], "products": []}} for p in profiles}
    for p in profiles[:40]:
        bought[p["customer_id"]]["dog"]["categories"] = ["treats"]
    for p in profiles[40:]:
        bought[p["customer_id"]]["dog"]["categories"] = ["treats"] if int(p["customer_id"][1:]) < 36 else []

    row = selection_preferences({f"D{i}" for i in range(40)}, {p["customer_id"]: {"dog"} for p in profiles}, bought)["dog"]["categories"][0]

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


# ── Review of #142 and the segment view ──

from src.customer_segments import bootstrap_mean_interval


def test_a_profit_interval_brackets_the_mean_and_is_wider_for_a_skewed_group():
    even = [50.0] * 40
    skewed = [10.0] * 36 + [400.0] * 4

    low, high = bootstrap_mean_interval(skewed)

    assert low < sum(skewed) / len(skewed) < high
    assert bootstrap_mean_interval(even) == [50.0, 50.0]
    assert high - low > 20


def test_a_group_under_thirty_customers_has_no_profit_interval():
    assert bootstrap_mean_interval([10.0] * (THIN_BELOW - 1)) is None


def test_the_interval_is_the_same_every_time():
    values = [float(v) for v in range(1, 61)]

    assert bootstrap_mean_interval(values) == bootstrap_mean_interval(values)


from src.customer_funnel import funnel_by_segment


def test_a_segments_funnel_counts_each_stage_over_the_showings_of_its_customers_only():
    showings = [{"context": "S1", "clicked": True, "added_to_cart": True, "purchased": True},
                {"context": "S1", "clicked": True, "added_to_cart": False, "purchased": False},
                {"context": "S2", "clicked": False, "added_to_cart": False, "purchased": False},
                {"context": "S3", "clicked": True, "added_to_cart": True, "purchased": True}]
    customer_of = {"S1": "C1", "S2": "C2", "S3": None}
    segments = {"C1": ["all", "offer:mostly"], "C2": ["all"]}

    result = funnel_by_segment(showings, customer_of, segments)

    assert result["offer:mostly"] == {"impressions": 2, "clicks": 2, "carts": 1, "purchases": 1}
    assert result["all"]["impressions"] == 3, "the anonymous session S3 is in no segment"


from src.customer_preference_ranking import GROUPS, ranking


def _ranked(shares: dict[str, float], segments_of=None):
    return ranking(shares, segments_of or {}, ["a", "b"])


def test_the_ranking_puts_the_customers_with_the_biggest_share_in_the_top_fifth():
    shares = {f"C{i:02d}": float(i) for i in range(1, 101)}

    result = _ranked(shares)

    assert result["quintiles"][0]["mean_share"] > result["quintiles"][-1]["mean_share"]
    assert [q["customers"] for q in result["quintiles"]] == [20] * GROUPS
    assert result["curve"][0] > result["curve"][-1] and len(result["curve"]) == 20


def test_the_top_fifth_is_given_over_the_average_and_over_the_bottom_fifth():
    shares = {f"C{i:03d}": (4.0 if i < 20 else 1.0) for i in range(100)}

    result = _ranked(shares)

    assert result["top_over_bottom"] == 4.0 and result["top_over_average"] == round(4.0 / 1.6, 2)


def test_when_the_bottom_fifth_has_none_the_ratio_to_it_is_left_out_and_not_infinite():
    shares = {f"C{i:03d}": (0.0 if i >= 30 else 0.5) for i in range(100)}

    assert _ranked(shares)["top_over_bottom"] is None


def test_each_quintile_says_how_many_of_a_segment_it_holds():
    shares = {f"C{i:02d}": float(100 - i) for i in range(100)}
    segments_of = {f"C{i:02d}": (["a"] if i < 20 else ["b"]) for i in range(100)}

    quintiles = _ranked(shares, segments_of)["quintiles"]

    assert quintiles[0]["segment_share"] == {"a": 1.0, "b": 0.0}
    assert quintiles[1]["segment_share"] == {"a": 0.0, "b": 1.0}


def test_a_ranking_of_nothing_is_an_error_not_a_flat_line():
    with pytest.raises(ValueError, match="nothing to rank"):
        _ranked({f"C{i}": 0.0 for i in range(10)})


def test_the_stored_ranking_has_the_offer_preference_and_a_top_fifth_that_prefers_it_more():
    ranked = chosen(["offer:mostly"])["ranking"]["offer"]

    assert ranked["top_over_average"] > 1.5 and ranked["curve"][0] > ranked["curve"][-1]


def test_a_segments_ranking_names_the_variable_it_is_a_slice_of():
    assert chosen(["price:premium-leaning"])["ranking"]["cheaper"]["label"].startswith("Lines in the cheaper half")
    assert chosen(["pets:dog"])["ranking"] == {}, "a pet is not a share of what a customer bought"


# ── Acquisition: where a segment's customers came from ──

from src.customer_acquisition import NO_CATEGORY, acquisition_by_segment, first_sessions


def _ctx(cid: str, visitor: str, month: str, source: str, landing: str = "product", category: str | None = "treats") -> dict:
    return {"context_id": cid, "visitor": visitor, "month": month, "source": source, "landing": landing, "landing_category": category}


def test_a_customers_first_session_is_the_earliest_of_their_visitors_sessions():
    contexts = [_ctx("S2", "V1", "2025-03", "email"), _ctx("S1", "V1", "2025-01", "paid_search", "offer", None), _ctx("S9", "V2", "2024-01", "direct")]

    found = first_sessions([{"customer_id": "C1", "visitor": "V1"}, {"customer_id": "C3", "visitor": "V404"}], contexts)

    assert found == {"C1": {"source": "paid_search", "landing": "offer", "landing_category": NO_CATEGORY}}


def _people(n_in: int, n_out: int, in_social: int, out_social: int):
    first, segments_of, profit = {}, {}, {}
    for i in range(n_in):
        first[f"I{i}"] = {"source": "social" if i < in_social else "direct", "landing": "product", "landing_category": "treats"}
        segments_of[f"I{i}"] = ["all", "offer:mostly"]
        profit[f"I{i}"] = 40.0
    for i in range(n_out):
        first[f"O{i}"] = {"source": "social" if i < out_social else "direct", "landing": "product", "landing_category": "treats"}
        segments_of[f"O{i}"] = ["all"]
        profit[f"O{i}"] = 90.0
    return first, segments_of, profit


def test_a_segment_that_comes_mostly_from_one_channel_has_that_channel_over_represented_beyond_its_margin():
    first, segments_of, profit = _people(60, 300, in_social=30, out_social=30)

    rows = acquisition_by_segment(first, segments_of, profit, ["offer:mostly"])["offer:mostly"]["source"]
    social = next(r for r in rows if r["value"] == "social")

    assert (social["share"], social["share_others"], social["points"]) == (0.5, 0.1, 40.0)
    assert social["clear"] is True


def test_a_difference_inside_its_margin_is_not_clear_in_acquisition():
    first, segments_of, profit = _people(60, 300, in_social=12, out_social=54)

    social = next(r for r in acquisition_by_segment(first, segments_of, profit, ["offer:mostly"])["offer:mostly"]["source"] if r["value"] == "social")

    assert social["points"] == 2.0 and social["clear"] is False


def test_profit_per_customer_by_channel_is_given_only_where_thirty_customers_stand_behind_it():
    first, segments_of, profit = _people(60, 300, in_social=10, out_social=0)

    rows = {r["value"]: r for r in acquisition_by_segment(first, segments_of, profit, ["offer:mostly"])["offer:mostly"]["source"]}

    assert rows["social"]["profit_per_customer_eur"] is None, "10 customers"
    assert rows["direct"]["profit_per_customer_eur"] == 40.0 and rows["direct"]["profit_per_customer_all_eur"] == round((50 * 40 + 300 * 90) / 350, 2)


def test_a_segment_under_the_minimum_has_no_acquisition_rows():
    first, segments_of, profit = _people(20, 300, in_social=5, out_social=30)

    assert "offer:mostly" not in acquisition_by_segment(first, segments_of, profit, ["offer:mostly"])


def test_every_profiled_customer_has_a_first_session_whose_source_is_their_first_source():
    customers = [c for c in json.loads((DATA / "customers.json").read_text()) if c["consent_behavioural"]]
    found = first_sessions(customers, json.loads((DATA / "contexts.json").read_text()))

    assert len(found) == len(customers)
    assert all(found[c["customer_id"]]["source"] == c["first_source"] for c in customers)


def test_the_stored_acquisition_shares_of_everyone_add_up_to_one_per_dimension():
    everyone = chosen([])["acquisition"]

    for dim, rows in everyone.items():
        assert abs(sum(r["share"] for r in rows) - 1.0) < 0.02, dim


# --- margin: a customer's basket margin, high or low against the median customer (ADR 0053, topic tree) ---

def test_a_customer_is_high_or_low_margin_against_the_median_of_the_profiled_customers():
    earned = {"A": {"net_revenue_eur": 100.0, "gross_profit_eur": 40.0}, "B": {"net_revenue_eur": 100.0, "gross_profit_eur": 30.0},
              "C": {"net_revenue_eur": 100.0, "gross_profit_eur": 20.0}}

    bands, cut = margin_bands(earned, ["A", "B", "C"])

    assert cut == 0.3 and bands == {"A": "high-margin", "B": "high-margin", "C": "low-margin"}


def test_a_customer_with_no_revenue_has_no_margin_and_does_not_move_the_median():
    earned = {"A": {"net_revenue_eur": 100.0, "gross_profit_eur": 40.0}, "B": {"net_revenue_eur": 100.0, "gross_profit_eur": 20.0},
              "Z": {"net_revenue_eur": 0.0, "gross_profit_eur": 0.0}}

    bands, cut = margin_bands(earned, ["A", "B", "Z", "NEVER-BOUGHT"])

    assert bands["Z"] == TOO_FEW and bands["NEVER-BOUGHT"] == TOO_FEW and cut == 0.3


def test_a_profile_with_a_margin_band_is_in_the_margin_segment():
    profile = {**traits([("A", True)] * 4), "margin": "high-margin"}

    assert "margin:high-margin" in segment_keys(profile)
