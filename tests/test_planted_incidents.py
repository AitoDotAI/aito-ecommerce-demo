"""Planted incidents (ADR 0056): a loud recall and three quiet quality problems, each behind its own switch."""

from types import SimpleNamespace

import pytest

from data import incidents, planted_switches


def product(sku, pet="dog", category="dry-food", brand="Acana", name="X Grain Free Salmon Dog Food 2kg", dietary="grain-free"):
    return SimpleNamespace(sku=sku, pet_type=pet, category=category, brand=brand, name=name, dietary=dietary)


@pytest.fixture
def catalogue():
    return (
        [product(f"D{i}", name=f"Acana Grain Free Salmon Dog Food {i}kg") for i in range(4)]
        + [product(f"C{i}", pet="cat", category="wet-food", brand="Sheba", name="Sheba Sensitive Beef Cat Food", dietary=None) for i in range(3)]
        + [product(f"T{i}", category="treats", brand="PetNord", name="PetNord Cheese Treats 200g", dietary=None) for i in range(3)]
        + [product(f"H{i}", pet="small_animal", brand="PetNord", name="PetNord Hamster Mix Food 4kg", dietary=None) for i in range(3)]
        + [product("OTHER", name="Hill's Chicken Dog Food 2kg", dietary="grain-free")]
    )


@pytest.fixture
def planned(catalogue):
    return incidents.plan(catalogue)


@pytest.fixture
def all_off(monkeypatch):
    for switch in ("E1", "E2", "E3", "E4"):
        monkeypatch.setitem(planted_switches.ON, switch, False)


@pytest.fixture
def all_on(monkeypatch):
    for switch in ("E1", "E2", "E3", "E4"):
        monkeypatch.setitem(planted_switches.ON, switch, True)


def test_each_incident_has_its_own_line_of_several_products_and_the_lines_do_not_overlap(planned):
    lines = [i.skus for i in planned]

    assert [len(line) >= incidents.EXPECTED_MIN_SKUS for line in lines] == [True] * 4
    assert sum(len(line) for line in lines) == len(frozenset().union(*lines))


def test_a_line_too_thin_to_leave_a_mark_fails_loudly(catalogue):
    with pytest.raises(AssertionError, match="incident line"):
        incidents.plan([p for p in catalogue if p.sku != "D0" and p.sku != "D1"])


def test_with_the_switches_off_nothing_changes(planned, all_off):
    hits = {}

    assert incidents.experience(planned, 42, "good", "L1", "D0", "2025-09", "CUST-1", hits) == "good"
    assert incidents.purchase_odds(planned, hits, "CUST-1", product("D0"), "2025-12") == 1.0
    assert incidents.withdrawn(planned, "D0", "2026-01") is False
    assert incidents.pick_factor(planned, "D0", "2025-09") == 1.0
    assert hits == {}


def test_a_purchase_of_the_recalled_line_in_a_batch_month_goes_badly_about_a_third_of_the_time(planned, all_on):
    hits = {}
    experiences = [incidents.experience(planned, 42, "good", f"L{n}", "D0", "2025-09", f"C{n}", hits) for n in range(2000)]

    assert 0.30 < experiences.count("bad") / 2000 < 0.40
    assert len(hits) == experiences.count("bad"), "every bad unit is noted against its customer"


def test_outside_the_incident_months_and_on_other_products_the_experience_is_untouched(planned, all_on):
    hits = {}

    assert all(incidents.experience(planned, 42, "good", f"L{n}", "D0", "2025-08", "C", hits) == "good" for n in range(200))
    assert all(incidents.experience(planned, 42, "good", f"L{n}", "OTHER", "2025-09", "C", hits) == "good" for n in range(200))


def test_the_same_line_always_draws_the_same_experience(planned, all_on):
    first = [incidents.experience(planned, 42, "ok", f"L{n}", "C0", "2025-02", "C", {}) for n in range(100)]
    again = [incidents.experience(planned, 42, "ok", f"L{n}", "C0", "2025-02", "C", {}) for n in range(100)]

    assert first == again


def test_the_recalled_line_is_not_on_sale_from_the_month_it_is_pulled_and_the_quiet_ones_never_are_pulled(planned, all_on):
    assert not incidents.withdrawn(planned, "D0", "2025-10")
    assert incidents.withdrawn(planned, "D0", "2025-11") and incidents.withdrawn(planned, "D0", "2026-04")
    assert not any(incidents.withdrawn(planned, sku, "2026-04") for sku in ("C0", "T0", "H0", "OTHER"))


def test_a_customer_with_a_bad_unit_nearly_stops_buying_that_line_for_a_year_and_then_is_as_before(planned, all_on):
    hits = {("CUST-1", "E2"): "2025-02"}
    cat = product("C0", pet="cat", category="wet-food", brand="Sheba", name="Sheba Sensitive Beef Cat Food", dietary=None)

    assert incidents.purchase_odds(planned, hits, "CUST-1", cat, "2025-03") == incidents.SWITCH_ODDS
    assert incidents.purchase_odds(planned, hits, "CUST-1", cat, "2026-02") == incidents.SWITCH_ODDS
    assert incidents.purchase_odds(planned, hits, "CUST-1", cat, "2026-03") == 1.0
    assert incidents.purchase_odds(planned, hits, "CUST-2", cat, "2025-03") == 1.0, "only the customer who had the bad unit switches"
    assert incidents.purchase_odds(planned, hits, "CUST-1", product("OTHER"), "2025-03") == 1.0, "other products are not affected"


def test_after_the_pull_trust_in_other_grain_free_dog_food_dips_and_recovers_in_eight_months(planned, all_on):
    other = product("OTHER")
    odds = [incidents.purchase_odds(planned, {}, "C", other, m) for m in ("2025-10", "2025-11", "2026-03", "2026-07")]

    assert odds[0] == 1.0, "before the news nothing has happened"
    assert odds[1] == pytest.approx(incidents.TRUST_ODDS)
    assert odds[1] < odds[2] < 1.0
    assert odds[3] == 1.0


def test_customers_who_bought_the_batch_trust_the_type_less_than_the_rest(planned, all_on):
    other = product("OTHER")
    hits = {("C", "E1"): "2025-10"}

    assert incidents.purchase_odds(planned, hits, "C", other, "2025-11") == pytest.approx(incidents.TRUST_ODDS * incidents.BATCH_BUYER_ODDS)


def test_the_recalled_line_sells_better_before_it_fails(planned, all_on):
    assert incidents.pick_factor(planned, "D0", "2025-01") == incidents.LINE_PICK_FACTOR
    assert incidents.pick_factor(planned, "D0", "2024-12") == 1.0
    assert incidents.pick_factor(planned, "OTHER", "2025-06") == 1.0


def test_the_recalled_line_is_written_under_the_house_label_and_nothing_else_is_renamed(catalogue, planned, all_on):
    incidents.rename_for_output(catalogue, planned)

    recalled = [p for p in catalogue if p.sku.startswith("D")]
    assert {p.brand for p in recalled} == {incidents.HOUSE_LABEL}
    assert [p.name for p in recalled][:2] == ["PetNord Grain Free Salmon Adult Dog Food 0kg", "PetNord Grain Free Salmon Adult Dog Food 1kg"]
    assert next(p for p in catalogue if p.sku == "OTHER").brand == "Acana"


def test_the_answer_key_lists_the_customers_who_had_a_bad_unit(planned, all_on):
    rows = incidents.answer_key_rows(planned, {("CUST-1", "E2"): "2025-02", ("CUST-2", "E2"): "2025-02"})

    assert next(r for r in rows if r["id"] == "E2")["customers_with_a_bad_unit"] == ["CUST-1", "CUST-2"]
    assert next(r for r in rows if r["id"] == "E1")["customers_with_a_bad_unit"] == []


def test_the_answer_key_lists_every_incident_and_says_which_are_planted(planned, all_off, monkeypatch):
    monkeypatch.setitem(planted_switches.ON, "E2", True)

    rows = incidents.answer_key_rows(planned, {})

    assert {r["id"]: r["planted"] for r in rows} == {"E1": False, "E2": True, "E3": False, "E4": False}


def test_a_bad_unit_from_the_recalled_batch_raises_the_churn_hazard_far_more_and_for_longer_than_an_ordinary_bad_experience(planned, all_on):
    assert incidents.recall_churn_rise(planned, "D0", "2025-09", "bad") == (incidents.RECALL_CHURN_RISE, incidents.RECALL_CHURN_MONTHS)
    assert incidents.recall_churn_rise(planned, "D0", "2025-09", "good") is None
    assert incidents.recall_churn_rise(planned, "D0", "2025-08", "bad") is None, "outside the batch months"
    assert incidents.recall_churn_rise(planned, "C0", "2025-02", "bad") is None, "a quiet incident makes customers switch, not leave"
    assert incidents.RECALL_CHURN_RISE > 3.0 and incidents.RECALL_CHURN_MONTHS > 3, "more than the ordinary rise of ×3 for 3 months"


def test_with_the_recall_off_a_bad_unit_has_no_extra_churn(planned, all_off):
    assert incidents.recall_churn_rise(planned, "D0", "2025-09", "bad") is None


def test_the_dog_treat_incident_runs_for_two_months_so_enough_customers_have_a_bad_unit_to_judge(planned):
    assert next(i for i in planned if i.id == "E3").months == ("2025-06", "2025-07")


def test_the_recalled_line_is_written_under_the_house_label_in_any_text_about_it_and_other_products_keep_their_names(catalogue, planned, all_on):
    recalled = next(p for p in catalogue if p.sku == "D1")
    other = next(p for p in catalogue if p.sku == "OTHER")

    assert incidents.display_name(planned, recalled) == "PetNord Grain Free Salmon Adult Dog Food 1kg"
    assert incidents.display_name(planned, other) == other.name


def test_with_the_recall_off_no_product_changes_its_name(catalogue, planned, all_off):
    assert all(incidents.display_name(planned, p) == p.name for p in catalogue)


def test_a_demo_anchor_is_never_part_of_an_incident_line(catalogue):
    anchored = incidents.plan(catalogue, anchors=frozenset({"D0"}))

    assert "D0" not in next(i for i in anchored if i.id == "E1").skus


def test_the_recalled_lines_house_label_names_are_unique_even_when_pack_sizes_repeat(all_on):
    twins = [product("A", name="Acana Grain Free Salmon Dog Food 2kg"), product("B", name="Hill's Grain Free Salmon Dog Food 2kg"),
             product("C", name="Eukanuba Grain Free Salmon Dog Food 12kg"), product("D", name="Orijen Grain Free Salmon Dog Food 12kg")]
    plan = incidents.plan(twins + [product(f"C{i}", pet="cat", category="wet-food", brand="Sheba", name="Sheba Beef Cat Food", dietary=None) for i in range(3)]
                          + [product(f"T{i}", category="treats", brand="PetNord", name="PetNord Treats", dietary=None) for i in range(3)]
                          + [product(f"H{i}", pet="small_animal", brand="PetNord", name="PetNord Hamster Mix Food 4kg", dietary=None) for i in range(3)])

    names = [incidents.display_name(plan, p) for p in twins]

    assert len(set(names)) == 4 and names[0] == "PetNord Grain Free Salmon Adult Dog Food 2kg" and names[1].endswith("2kg, recipe 2")
