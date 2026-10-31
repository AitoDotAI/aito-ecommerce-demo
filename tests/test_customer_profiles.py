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
    state = {"on_offer": on_offer, "price_eur": PRODUCTS[sku]["price_eur"]}
    return {"product_sku": sku, "product_state": f"{sku}-{on_offer}"}, state


def traits(skus_and_offers: list[tuple[str, bool]], consent: bool = True) -> dict:
    pairs = [line(sku, offer) for sku, offer in skus_and_offers]
    states = {ln["product_state"]: st for ln, st in pairs}
    customer = {"customer_id": "C1", "name": "Test Person", "consent_behavioural": consent, "pets": None}
    return traits_for(customer, [ln for ln, _ in pairs], PRODUCTS, states, REF)


def test_the_bands_cut_where_the_action_table_cuts():
    assert [offer_band(x) for x in (0.0, 0.19, 0.2, 0.39, 0.4, 1.0)] == ["rarely", "rarely", "sometimes", "sometimes", "mostly", "mostly"]
    assert (price_band(0.7), price_band(0.5), price_band(0.6)) == ("value-leaning", "premium-leaning", "mixed")
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
    customers = {"C1": {"churned": True, "total_spent_eur": 100.0}, "C2": {"churned": False, "total_spent_eur": 300.0}}
    profiles = [{"customer_id": cid, "profiled": True, "offer": "mostly", "price": "mixed", "rating": "average ratings",
                 "pets": ["dog"], "diets": []} for cid in customers]

    result = segments(profiles, customers)["by_trait"]["offer"][0]

    assert (result["customers"], result["churn_rate"], result["avg_spend_eur"], result["thin"]) == (2, 0.5, 200.0, True)


def rows(action: str, ordered: int, total: int, value: str = "yes") -> list[dict]:
    return [{"offer_buyer": value, "recency_bucket": "0-90d", "email_history": "never_sent", "tracking_consent": "yes",
             "spend_band": "mid", "open_issue": "none", "action": action, "purchased_30d": i < ordered} for i in range(total)]


def test_a_response_lift_is_the_difference_to_no_action_in_points_with_its_margin():
    cell = response(rows("none", 20, 100) + rows("discount", 40, 100))["offer_buyer"][0]["actions"]["discount"]

    assert cell["lift_points"] == 20.0 and cell["clear"] is True and 0 < cell["margin_points"] < 20


def test_a_lift_inside_its_margin_is_not_called_clear():
    cell = response(rows("none", 20, 100) + rows("email", 24, 100))["offer_buyer"][0]["actions"]["email"]

    assert cell["lift_points"] == 4.0 and cell["clear"] is False


def test_a_cell_with_few_rows_has_no_lift_at_all():
    cell = response(rows("none", 20, 100) + rows("ad", 5, THIN_BELOW - 1))["offer_buyer"][0]["actions"]["ad"]

    assert cell["thin"] is True and cell["lift_points"] is None and cell["clear"] is None


def test_the_planted_discount_effect_shows_where_it_was_planted():
    """A2: a discount helps shoppers who mostly buy on offer, and does not help those who rarely do."""
    stored = json.loads((PROFILES / "summary.json").read_text())["response"]["offer_buyer"]
    by_value = {e["value"]: e["actions"]["discount"] for e in stored}

    assert by_value["mostly"]["clear"] is True and by_value["mostly"]["lift_points"] > 5
    assert by_value["rarely"]["clear"] is False


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
    assert api.get(f"/api/customer-profiles/customers/{unprofiled['customer_id']}").json()["offer"] == NOT_PROFILED
    assert api.get("/api/customer-profiles/customers/CUST-NOPE").status_code == 404


def test_a_lookup_needs_two_letters(api):
    assert api.get("/api/customer-profiles/customers", params={"q": "a"}).json() == {"customers": []}
