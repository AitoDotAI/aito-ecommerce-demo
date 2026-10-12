"""Data checks for ADR 0030's planted effects (S1–S7).

The thresholds are pre-registered in
`docs/verification/shoppers-data-prereg.md`, before the generator
changed. These tests read the on-disk fixtures, like `test_fixtures.py`.
Whether Aito *recovers* each effect is checked separately, against the
loaded data (`tests/test_aito_check.py`).
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import pytest

from data import lifecycle, shoppers

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FOOD = {"dry-food", "wet-food"}
RULE_WORDS = {"grain-free": "Grain Free", "sensitive": "Sensitive", "senior": "Senior", "puppy": "Puppy"}


def _load(name: str) -> list[dict]:
    with (DATA_DIR / name).open(encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def data():
    products = {p["sku"]: p for p in _load("products.json")}
    customers = {c["customer_id"]: c for c in _load("customers.json")}
    orders = sorted(_load("orders.json"), key=lambda o: (o["customer_id"], o["month"]))
    lines_by_order = defaultdict(list)
    for line in _load("order_lines.json"):
        lines_by_order[line["order_id"]].append(products[line["product_sku"]])
    orders_by_customer = defaultdict(list)
    for o in orders:
        orders_by_customer[o["customer_id"]].append(o)
    return products, customers, orders, lines_by_order, orders_by_customer


@pytest.fixture(scope="module")
def impressions():
    return _load("impressions.json")


def test_s1_diet_rule_households_only_ever_buy_food_that_keeps_the_rule(data):
    products, customers, orders, lines_by_order, _ = data
    broken = [
        (o["customer_id"], p["name"])
        for o in orders
        if (rule := customers[o["customer_id"]].get("diet_rule"))
        for p in lines_by_order[o["order_id"]]
        if p["pet_type"] in ("dog", "cat") and p["category"] in FOOD and RULE_WORDS[rule] not in p["name"]
    ]
    assert broken == [], broken[:5]


def test_s1_diet_rule_households_never_buy_rule_breaking_food_from_an_impression(data, impressions):
    products, *_ = data
    broken = [
        i["impression_id"] for i in impressions
        if (rule := i.get("customer_diet_rule")) and i["purchased"]
        and (p := products[i["product_sku"]])["pet_type"] in ("dog", "cat") and p["category"] in FOOD
        and RULE_WORDS[rule] not in p["name"]
    ]
    assert broken == [], f"{len(broken)} rule-breaking purchases, e.g. {broken[:3]}"


def test_s1_a_fifth_of_dog_and_cat_households_have_a_rule(data):
    _, customers, *_ = data
    households = [c for c in customers.values() if c["segment"] in ("dog_owner", "cat_owner", "multi_pet")]
    share = sum("diet_rule" in c for c in households) / len(households)
    assert 0.15 <= share <= 0.25, f"{share:.1%}"


def test_s2_small_animal_add_ons_follow_the_kit_in_order(data):
    *_, lines_by_order, orders_by_customer = data
    sequence = lifecycle.ADD_ONS["small_animal"]
    followed = total = 0
    for orders in orders_by_customer.values():
        bought: list[str] = []
        for o in orders:
            for p in lines_by_order[o["order_id"]]:
                kind = lifecycle.item_type(p["name"], p["brand"])
                if p["pet_type"] == "small_animal" and kind in sequence and kind not in bought:
                    bought.append(kind)
        if len(bought) >= 2 and bought[0] != sequence[-1]:
            total += 1
            followed += bought[1] == sequence[sequence.index(bought[0]) + 1]
    assert total >= 30, total
    assert followed / total >= 0.70, f"{followed}/{total}"


def _share(orders, lines_by_order, months: set[int], categories: set[str]) -> float:
    lines = [p for o in orders if int(o["month"][5:]) in months for p in lines_by_order[o["order_id"]]]
    return sum(p["category"] in categories for p in lines) / len(lines)


def test_s4_treats_and_toys_peak_in_december(data):
    _, _, orders, lines_by_order, _ = data
    gifts = {"treats", "toys"}
    ratio = _share(orders, lines_by_order, {12}, gifts) / _share(orders, lines_by_order, set(range(3, 11)), gifts)
    assert ratio >= 1.6, f"{ratio:.2f}"


def test_s4_grooming_and_health_peak_in_summer(data):
    _, _, orders, lines_by_order, _ = data
    summer_care = {"grooming", "health"}
    ratio = (_share(orders, lines_by_order, {6, 7, 8}, summer_care)
             / _share(orders, lines_by_order, {10, 11, 12, 1, 2, 3, 4}, summer_care))
    assert ratio >= 1.4, f"{ratio:.2f}"


def test_s5_a_poorly_made_food_is_rebought_less(data):
    *_, lines_by_order, orders_by_customer = data
    rebuys = {True: [0, 0], False: [0, 0]}   # poor? → [re-bought, food lines]
    for orders in orders_by_customer.values():
        seen: set[str] = set()
        for o in orders:
            for p in lines_by_order[o["order_id"]]:
                if p["category"] in FOOD:
                    tally = rebuys[shoppers.is_poorly_made(p["sku"])]
                    tally[0] += p["sku"] in seen
                    tally[1] += 1
                    seen.add(p["sku"])
    poor, rest = (rebuys[k][0] / rebuys[k][1] for k in (True, False))
    assert poor / rest <= 0.8, f"poor {poor:.1%} vs rest {rest:.1%}"


def test_s5_a_poorly_made_product_converts_less_from_an_impression(impressions):
    bought = {True: [0, 0], False: [0, 0]}
    for i in impressions:
        tally = bought[shoppers.is_poorly_made(i["product_sku"])]
        tally[0] += i["purchased"]
        tally[1] += 1
    poor, rest = (bought[k][0] / bought[k][1] for k in (True, False))
    assert poor / rest <= 0.7, f"poor {poor:.2%} vs rest {rest:.2%}"


def test_s5_products_carry_the_rating_their_reviews_give(data):
    products, *_ = data
    rated = [p for p in products.values() if "avg_rating" in p]
    assert len(rated) >= 0.8 * len(products)
    assert {p["rating_band"] for p in products.values()} <= {"1-2", "3", "4", "5", "unrated"}


def test_s6_a_complement_of_the_basket_converts_more(data, impressions):
    products, *_ = data
    rates = defaultdict(lambda: [0, 0])   # (surface, complement?) → [bought, shown]
    for i in impressions:
        basket = i.get("basket_categories", "").split()
        complement = shoppers.complements_basket(products[i["product_sku"]], basket)
        tally = rates[(i["surface"], complement)]
        tally[0] += i["purchased"]
        tally[1] += 1
    surfaces = {s for s, c in rates if c and rates[(s, True)][1] >= 200}
    assert surfaces, "no surface shows enough complements to compare"
    for s in surfaces:
        comp = rates[(s, True)][0] / rates[(s, True)][1]
        rest = rates[(s, False)][0] / rates[(s, False)][1]
        assert comp / rest >= 1.6, f"{s}: complement {comp:.1%} vs rest {rest:.1%}"


def test_s7_search_queries_are_words_from_the_products(data, impressions):
    products, *_ = data
    queries = {i["search_query"] for i in impressions if i["surface"] == "search"}
    assert sum(len(q.split()) >= 2 for q in queries) / len(queries) >= 0.90
    names = [p["name"].lower() for p in products.values()]
    for q in queries:
        matching = sum(all(word in name for word in q.split()) for name in names)
        assert matching >= 3, f"{q!r} matches {matching} products"
