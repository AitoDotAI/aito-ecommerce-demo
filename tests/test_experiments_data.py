"""The experiments' data (ADR 0064): the plan, the showings, and the planted reactions the evidence has to find."""
import json
from collections import defaultdict
from pathlib import Path

import pytest

from data.experiments import ARMS, LIFT, gen_experiments, margin, plan_experiments, signal_of, true_chance, wellness_shares

DATA = Path(__file__).resolve().parent.parent / "data"
MONTHS = ["2026-01", "2026-02", "2026-03", "2026-04"]
PRODUCTS = [{"sku": f"P{i:02d}", "name": f"Dog Food {i}", "category": "dry-food", "pet_type": "dog", "price_eur": 10.0 + i, "dietary": None} for i in range(14)]
UNITS = {p["sku"]: 100 - i for i, p in enumerate(PRODUCTS)}
COST = {p["sku"]: 6.0 for p in PRODUCTS}


def customer(i: int, consent: bool = True, level: str = "mid") -> dict:
    return {"customer_id": f"C{i:03d}", "consent": consent, "pets": ["dog"], "first_source": "direct",
            "hidden": {"discount": level, "health_focus": "medium", "newness": level}}


def small_world() -> dict:
    customers = [customer(i, consent=i % 5 != 0, level=("high", "mid", "low")[i % 3]) for i in range(300)]
    return gen_experiments(1, customers, PRODUCTS, COST, UNITS, {}, {}, MONTHS)


def test_twelve_experiments_are_planned_on_the_best_sellers_of_three_kinds_two_of_them_drafts_and_two_decided():
    plans = plan_experiments(PRODUCTS, UNITS, MONTHS)
    assert [p.sku for p in plans] == [f"P{i:02d}" for i in range(12)]
    assert {p.kind for p in plans} == {"offer", "title", "image"}
    assert [p.status for p in plans].count("draft") == 2 and [p.status for p in plans].count("decided") == 2
    assert all(p.decided_month == MONTHS[1] for p in plans if p.status == "decided")


def test_a_shopper_who_did_not_consent_is_shown_nothing_and_a_draft_has_no_showings():
    world = small_world()
    refused = {f"C{i:03d}" for i in range(300) if i % 5 == 0}
    assert not refused & {s["customer"] for s in world["experiment_showings"]}
    drafts = {e["experiment_id"] for e in world["experiments"] if e["status"] == "draft"}
    assert drafts and not drafts & {s["experiment"] for s in world["experiment_showings"]}


def test_after_a_decision_the_winner_is_shown_about_nine_times_in_ten_and_the_other_arm_still_appears():
    world = small_world()
    decided = next(e for e in world["experiments"] if e["status"] == "decided")
    later = [s for s in world["experiment_showings"] if s["experiment"] == decided["experiment_id"] and s["month"] > MONTHS[1]]
    winner_share = sum(s["variant"].endswith(decided["decided_arm"]) for s in later) / len(later)
    assert 0.9 < winner_share < 1.0   # 90 % served, plus half of the 10 % drawn at random


def test_an_offer_arm_costs_margin_and_a_title_or_image_arm_does_not():
    assert margin("offer", "offer", 20.0, 12.0) == 5.0 and margin("offer", "list", 20.0, 12.0) == 8.0
    assert margin("title", "benefit", 20.0, 12.0) == margin("title", "plain", 20.0, 12.0) == 8.0


def test_the_planted_lift_applies_to_the_second_arm_only():
    hidden = {"discount": "high", "health_focus": "low", "newness": "mid"}
    assert true_chance("offer", "list", 0.05, hidden) == 0.05
    assert true_chance("offer", "offer", 0.05, hidden) == pytest.approx(0.05 * LIFT["offer"]["high"])
    assert true_chance("title", "benefit", 0.05, hidden) < 0.05      # a low health focus is put off by a benefit-led title


def test_what_the_shop_sees_is_the_offer_share_the_wellness_share_or_the_first_source():
    c = {"customer_id": "C1", "first_source": "social"}
    assert signal_of("offer", c, {"C1": "mostly"}, {}) == "mostly"
    assert signal_of("title", c, {}, {"C1": "some"}) == "some"
    assert signal_of("image", c, {}, {}) == "social"
    assert signal_of("offer", c, {}, {}) == "unknown"


def test_wellness_share_bands_count_kept_lines_only():
    orders = [{"order_id": "O1", "customer_id": "C1"}, {"order_id": "O2", "customer_id": "C2"}]
    lines = [{"order_id": "O1", "product_sku": "A", "returned": False}, {"order_id": "O1", "product_sku": "B", "returned": False},
             {"order_id": "O1", "product_sku": "A", "returned": True}, {"order_id": "O2", "product_sku": "B", "returned": False}]
    bands = wellness_shares(lines, orders, {"A": "senior", "B": None}, {"senior"})
    assert bands == {"C1": "most", "C2": "none"}


# ── the committed fixtures ─────────────────────────────────────────────────


def load(name: str):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def tables():
    return {name: load(f"{name}.json") for name in ("experiments", "experiment_variants", "experiment_showings")}


def test_every_showing_links_to_its_experiment_and_one_of_its_two_variants(tables):
    variants = {v["variant_id"]: v for v in tables["experiment_variants"]}
    experiments = {e["experiment_id"]: e for e in tables["experiments"]}
    assert len(variants) == 2 * len(experiments)
    for s in tables["experiment_showings"][:5000]:
        assert variants[s["variant"]]["experiment"] == s["experiment"] and experiments[s["experiment"]]["product_sku"] == s["product_sku"]
        assert s["signal_arm"] == f"{s['signal']}|{variants[s['variant']]['arm']}"


def test_only_customers_who_consented_were_shown_anything(tables):
    consented = {c["customer_id"] for c in load("customers.json") if c["consent_behavioural"]}
    assert {s["customer"] for s in tables["experiment_showings"]} <= consented


def test_the_planted_reactions_are_in_the_showings_for_each_kind(tables):
    """Among shoppers with a high level of the hidden trait the second arm sells about as many times better as planted, and not so among the low."""
    traits = {t["customer_id"]: t for t in load("answer_key/customer_traits.json")}
    trait = {"offer": "discount_sensitivity", "title": "health_focus", "image": "newness_sensitivity"}
    kind = {e["experiment_id"]: e["kind"] for e in tables["experiments"]}
    counts = defaultdict(lambda: [0, 0])
    for s in tables["experiment_showings"]:
        k = kind[s["experiment"]]
        arm = s["variant"].split(":")[1]
        cell = counts[k, traits[s["customer"]][trait[k]], arm == ARMS[k][1]]
        cell[0] += 1
        cell[1] += s["purchased"]
    ratio = lambda k, level: (counts[k, level, True][1] / counts[k, level, True][0]) / (counts[k, level, False][1] / counts[k, level, False][0])
    assert ratio("offer", "high") == pytest.approx(LIFT["offer"]["high"], rel=0.25)
    assert ratio("offer", "low") == pytest.approx(LIFT["offer"]["low"], rel=0.3)
    assert ratio("title", "high") == pytest.approx(LIFT["title"]["high"], rel=0.25)
    assert ratio("title", "low") < 1.0
    assert ratio("image", "high") == pytest.approx(LIFT["image"]["high"], rel=0.25)
