"""Data release 6, C2: fictional brands (docs/verification/release6-prereg.md, checks B1 and B2; data/rebrand.py).

B1 fails first: the whole-output scan must FIND the real brands in release 5 as committed, and find none once release 5
is written through the mapping. The real-data cases skip when data/ is not there (a fresh clone without fixtures).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from data.generate_fixtures import BRAND_CATEGORIES, MASS_BRANDS, PREMIUM_BRANDS
from data.rebrand import (HOUSE_LABEL, RELEASE6_BRANDS, Rebrander, check_mapping, product_name_map,
                          scan_for_real_brands)

DATA = Path(__file__).resolve().parents[1] / "data"


def _load(name: str):
    return json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))


have_data = pytest.mark.skipif(not (DATA / "products.json").exists(), reason="release 5 fixtures not present")


# ── B2: the mapping ───────────────────────────────────────────────


def test_the_mapping_covers_every_brand_but_the_house_label_one_to_one():
    check_mapping(RELEASE6_BRANDS, BRAND_CATEGORIES)
    assert HOUSE_LABEL in BRAND_CATEGORIES and HOUSE_LABEL not in RELEASE6_BRANDS


def test_the_tiers_are_kept_because_the_generator_draws_with_the_old_names():
    # the generator still draws with release 5's names (tiers, categories); only the writing maps them
    assert set(PREMIUM_BRANDS) - {HOUSE_LABEL} <= set(RELEASE6_BRANDS)
    assert set(MASS_BRANDS) - {HOUSE_LABEL} <= set(RELEASE6_BRANDS)


def test_a_broken_mapping_is_refused():
    with pytest.raises(ValueError, match="same name"):
        check_mapping({"Acana": "X", "Orijen": "X"})
    with pytest.raises(ValueError, match="contains a release-5 brand"):
        check_mapping({"Acana": "Kong Junior"})
    with pytest.raises(ValueError, match="house label"):
        check_mapping({"Acana": "PetNord"})
    with pytest.raises(ValueError, match="missing"):
        check_mapping({"Acana": "Tundrafield"}, ["Acana", "Orijen", "PetNord"])


# ── the rewrite ───────────────────────────────────────────────────


PRODUCTS = [
    {"sku": "S1", "name": "Royal Canin Chicken Dog Food 1kg", "brand": "Royal Canin"},
    {"sku": "S2", "name": "Royal Canin Chicken Dog Food 1kg, light recipe", "brand": "Royal Canin"},
    {"sku": "S3", "name": "Hill's Science Plan Indoor Salmon Cat Food 150g", "brand": "Hill's Science Plan"},
    {"sku": "S4", "name": "PetNord Clumping Clay Cat Litter 7kg", "brand": "PetNord"},
]


def test_names_brand_columns_and_texts_are_rewritten_and_nothing_else():
    r = Rebrander(product_name_map(PRODUCTS))
    rows = r.rows([
        {"name": "Royal Canin Chicken Dog Food 1kg, light recipe", "brand": "Royal Canin"},
        {"text": "Will the Hill's Science Plan Indoor Salmon Cat Food 150g come back? Better than the Royal Canin Chicken Dog Food 1kg."},
        {"product_brand": "Hill's Science Plan", "favorite_brands": ["Royal Canin", "PetNord"]},
        {"first_name": "Felix", "note": "Felix"},  # a person is not a brand: left alone, and the scan says so
        {"name": "PetNord Clumping Clay Cat Litter 7kg", "brand": "PetNord", "n": 3},
    ])
    assert rows[0] == {"name": "Aurelian Vet Chicken Dog Food 1kg, light recipe", "brand": "Aurelian Vet"}  # the longest name first
    assert rows[1]["text"] == ("Will the Fernholm Nutrition Plan Indoor Salmon Cat Food 150g come back? "
                               "Better than the Aurelian Vet Chicken Dog Food 1kg.")
    assert rows[2] == {"product_brand": "Fernholm Nutrition Plan", "favorite_brands": ["Aurelian Vet", "PetNord"]}
    assert rows[3] == {"first_name": "Felix", "note": "Felix"}
    assert rows[4] == {"name": "PetNord Clumping Clay Cat Litter 7kg", "brand": "PetNord", "n": 3}
    assert [w for w, _ in scan_for_real_brands(rows)] == ["[3].first_name", "[3].note"]


def test_a_name_that_does_not_start_with_its_brand_is_refused():
    with pytest.raises(ValueError, match="does not start with its brand"):
        product_name_map([{"sku": "S9", "name": "Dog Food by Acana", "brand": "Acana"}])


# ── B1: the whole-output scan ─────────────────────────────────────


@pytest.mark.parametrize("text", [
    "Royal Canin", "royal canin", "ROYAL-CANIN", "royal_canin", "royalcanin", "royal%20canin", "Royal+Canin",
    "Hill's", "Hill’s Science Plan", "hills-science-plan", "/products/hills-science-plan-indoor", "Hill%27s+Science+Plan",
    "kong", "KONG tug", "jbl-air-pump", "tetra", "Beaphar", "trixie_cage", "felix", "whimzees", "acana", "orijen", "whiskas",
    "sheba", "eukanuba",
])
def test_the_scan_finds_a_real_brand_in_any_spelling_a_page_slug_url_or_handle_uses(text):
    assert list(scan_for_real_brands({"alt": text})), text


@pytest.mark.parametrize("text", ["kongress", "tetrapod", "the hills", "felixstowe", "Shebang", "Aurelian Vet",
                                  "Tassuliini Leash", "PetNord", "Purrsy", "Rippleward Air Pump"])
def test_the_scan_does_not_flag_words_that_only_contain_the_letters(text):
    assert not list(scan_for_real_brands(text)), text


@have_data
def test_FAIL_FIRST_the_scan_finds_the_real_brands_in_release_5_as_committed():
    found = {t: sum(1 for _ in scan_for_real_brands(_load(t))) for t in ("products", "reviews", "nps_responses", "monthly_sales")}
    assert all(n > 0 for n in found.values()), found


@have_data
def test_release_5_written_through_the_mapping_scans_clean_in_every_table():
    """Every JSON file the release holds (data/*.json and data/answer_key/*.json; the git-ignored large ones when present)."""
    rebrander = Rebrander(product_name_map(_load("products")))
    files = sorted(DATA.glob("*.json")) + sorted((DATA / "answer_key").glob("*.json"))
    assert len(files) > 10
    survivors = {}
    for f in files:
        rows = json.loads(f.read_text(encoding="utf-8"))
        hits = list(scan_for_real_brands(rebrander.value(rows), f.name))
        if hits:
            survivors[f.name] = hits[:3]
    assert survivors == {}


@have_data
def test_the_mapping_changes_no_number_and_no_row_count():
    """S1's half that holds by construction: only strings change, so every number, key and length stays."""
    rebrander = Rebrander(product_name_map(_load("products")))

    def shape(v):
        if isinstance(v, dict):
            return {k: shape(x) for k, x in v.items()}
        if isinstance(v, list):
            return [shape(x) for x in v]
        return "<str>" if isinstance(v, str) else v

    for t in ("products", "order_lines", "reviews", "monthly_sales"):
        before = _load(t)
        assert shape(rebrander.rows(before)) == shape(before), t
