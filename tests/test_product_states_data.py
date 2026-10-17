"""ADR 0032's planted effects, checked on the generated fixtures.

Each test is one pre-registered check (docs/verification/product-states-prereg.md,
§1), with the threshold fixed there before the generator changed.
"""

import json
import statistics
from collections import defaultdict
from pathlib import Path

import pytest

from data.catalogue_events import LARGE_PACK_KG, SMALL_PACK_KG, add_months, pack_kg

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _load(name: str) -> list[dict]:
    path = DATA_DIR / name
    if not path.exists():
        pytest.skip(f"{name} missing — run `./do generate-fixtures`.")
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def states() -> dict[str, dict]:
    return {st["product_state_id"]: st for st in _load("product_states.json")}


@pytest.fixture(scope="module")
def impressions() -> list[dict]:
    return _load("impressions.json")


@pytest.fixture(scope="module")
def products() -> dict[str, dict]:
    return {p["sku"]: p for p in _load("products.json")}


@pytest.fixture(scope="module")
def launches(states) -> dict[str, str]:
    """sku → launch month, for products whose first state is after the window's first month."""
    first: dict[str, str] = {}
    for st in states.values():
        first[st["product_sku"]] = min(first.get(st["product_sku"], st["month"]), st["month"])
    window_start = min(first.values())
    return {sku: m for sku, m in first.items() if m > window_start}


def purchase_rate(rows) -> float:
    rows = list(rows)
    assert rows, "no impressions to rate"
    return sum(r["purchased"] for r in rows) / len(rows)


def test_p1a_an_offer_converts_budget_shoppers_far_more(impressions, states):
    budget = [r for r in impressions if r["customer_lifestyle"] == "budget"]
    on = purchase_rate(r for r in budget if states[r["product_state"]]["on_offer"])
    off = purchase_rate(r for r in budget if not states[r["product_state"]]["on_offer"])
    assert on / off >= 1.7, on / off


def test_p1b_premium_shoppers_respond_to_offers_much_less(impressions, states):
    def ratio(lifestyle):
        rows = [r for r in impressions if r["customer_lifestyle"] == lifestyle]
        on = purchase_rate(r for r in rows if states[r["product_state"]]["on_offer"])
        return on / purchase_rate(r for r in rows if not states[r["product_state"]]["on_offer"])

    assert ratio("premium") <= 1.35, ratio("premium")
    assert ratio("budget") / ratio("premium") >= 1.4, (ratio("budget"), ratio("premium"))


def test_p2a_nothing_of_a_launched_product_exists_before_its_launch(launches):
    assert len(launches) == 50
    month_of_order = {o["order_id"]: o["month"] for o in _load("orders.json")}
    dated = (
        [(r["product_sku"], r["month"]) for r in _load("impressions.json")]
        + [(r["product_sku"], month_of_order[r["order_id"]]) for r in _load("order_lines.json")]
        + [(r["product_sku"], r["month"]) for r in _load("monthly_sales.json")]
        + [(r["product_sku"], r["month"]) for r in _load("product_states.json")]
    )
    early = [(sku, m) for sku, m in dated if sku in launches and m < launches[sku]]
    assert not early, early[:5]


def test_p2b_a_new_product_sells_more_while_new_than_once_established(launches, products):
    """A launched product's share of its (pet, category)'s lines in its first
    3 months ÷ its own share in months 4–9, pooled over launches. (Amended:
    a fair share by product count is the wrong baseline for food, where
    households keep the food they settled on before a launch.)"""
    month_of_order = {o["order_id"]: o["month"] for o in _load("orders.json")}
    slice_of = {sku: (p["pet_type"], p["category"]) for sku, p in products.items()}
    slice_lines = defaultdict(int)       # (slice, month) → lines
    sku_lines = defaultdict(int)         # (sku, month) → lines
    for ln in _load("order_lines.json"):
        m = month_of_order[ln["order_id"]]
        slice_lines[(slice_of[ln["product_sku"]], m)] += 1
        sku_lines[(ln["product_sku"], m)] += 1

    def share(sku, months):
        total = sum(slice_lines[(slice_of[sku], m)] for m in months)
        return sum(sku_lines[(sku, m)] for m in months) / total if total else None

    new, established = [], []
    for sku, launch in launches.items():
        a = share(sku, [add_months(launch, i) for i in range(3)])
        b = share(sku, [add_months(launch, i) for i in range(3, 9)])
        if a is not None and b:
            new.append(a)
            established.append(b)
    assert sum(new) / sum(established) >= 1.5, (sum(new), sum(established))


def test_p2c_incumbents_sell_less_after_a_rival_launches(launches, products):
    """Incumbents' units 3 months after a launch ÷ 3 before, against the same
    months' ratio for slices with no launch around then."""
    slice_of = {sku: (p["pet_type"], p["category"]) for sku, p in products.items()}
    units = defaultdict(int)             # (slice, month) → units of products not launched in the window
    for ms in _load("monthly_sales.json"):
        if ms["product_sku"] not in launches:
            units[(slice_of[ms["product_sku"]], ms["month"])] += ms["units_sold"]
    launched_slices = defaultdict(set)   # slice → launch months
    for sku, m in launches.items():
        launched_slices[slice_of[sku]].add(m)
    all_slices = {s for s, _ in units}

    def after_over_before(slc, m):
        before = sum(units[(slc, add_months(m, -i))] for i in range(1, 4))
        after = sum(units[(slc, add_months(m, i))] for i in range(3))
        return after / before if before else None

    treated, control = [], []
    for slc, months in launched_slices.items():
        for m in months:
            r = after_over_before(slc, m)
            calm = [s for s in all_slices
                    if not any(abs(_index(m) - _index(lm)) <= 5 for lm in launched_slices.get(s, ()))]
            c = [x for x in (after_over_before(s, m) for s in calm) if x is not None]
            if r is not None and c:
                treated.append(r)
                control.append(statistics.mean(c))
    assert statistics.mean(treated) / statistics.mean(control) <= 0.95, (statistics.mean(treated), statistics.mean(control))


def _index(month: str) -> int:
    y, m = (int(x) for x in month.split("-"))
    return y * 12 + m


def test_p2d_flexible_shoppers_take_to_new_products(impressions, states, launches):
    """(Flexible ÷ loyal purchase rate on launched products while new) ÷ (the
    same once established). (Amended: loyal shoppers' rate differs on every
    product, so the raw ratio confounds the planted effect.)"""
    def ratio(age):
        rows = [r for r in impressions if r["product_sku"] in launches and states[r["product_state"]]["age"] == age]
        flexible = purchase_rate(r for r in rows if r["customer_brand_loyalty"] == "flexible")
        return flexible / purchase_rate(r for r in rows if r["customer_brand_loyalty"] == "loyal")

    assert ratio("new") / ratio("established") >= 1.3, (ratio("new"), ratio("established"))


def test_p3a_a_price_rise_lowers_sales(states, products, launches):
    raised = {}
    for st in states.values():
        if st["price_change"] == "rise":
            raised[st["product_sku"]] = min(raised.get(st["product_sku"], st["month"]), st["month"])
    assert len(raised) == 60
    units = {(ms["product_sku"], ms["month"]): ms["units_sold"] for ms in _load("monthly_sales.json")}

    def ratio(skus, m):
        before = sum(units.get((s, add_months(m, -i)), 0) for s in skus for i in range(1, 4))
        after = sum(units.get((s, add_months(m, i)), 0) for s in skus for i in range(3))
        return after / before if before else None

    relative = []
    for sku, m in raised.items():
        mine = ratio([sku], m)
        # Not launched mid-window: those go from no units to some (amended).
        peers = [s for s, p in products.items() if p["category"] == products[sku]["category"]
                 and s not in raised and s not in launches]
        theirs = ratio(peers, m)
        if mine is not None and theirs:
            relative.append((mine, theirs))
    assert sum(a for a, _ in relative) / sum(b for _, b in relative) <= 0.92


def test_p4a_stars_sell_within_the_same_product(impressions, states):
    """For each product with impressions in months it showed 5 stars and in
    months it showed 3: its purchase rate at 5 ÷ at 3, pooled. Fewer than 15
    such products: ≥ 4 stars against ≤ 3 instead, ≥ 1.1. (Amended: across
    products, those with few early reviews have extreme bands and sell less.)"""
    from data.shoppers import is_poorly_made
    by = defaultdict(lambda: [0, 0])     # (sku, band) → [purchases, impressions]
    for r in impressions:
        if not is_poorly_made(r["product_sku"]):
            cell = by[(r["product_sku"], states[r["product_state"]]["rating_band"])]
            cell[0] += r["purchased"]
            cell[1] += 1

    def pooled(high, low):
        skus = {sku for sku, _ in by}
        both = [s for s in skus if any(by[(s, b)][1] for b in high) and any(by[(s, b)][1] for b in low)]
        # Each product's rate at each level, weighted by its impressions at the lower level.
        num = den = 0.0
        for s in both:
            hp, hn = (sum(by[(s, b)][i] for b in high) for i in (0, 1))
            lp, ln = (sum(by[(s, b)][i] for b in low) for i in (0, 1))
            num += hp / hn * ln
            den += lp
        return len(both), (num / den if den else None)

    n, ratio = pooled(["5"], ["3"])
    if n >= 15:
        assert ratio >= 1.15, (n, ratio)
    else:
        n, ratio = pooled(["4", "5"], ["3", "1-2"])
        assert ratio >= 1.1, (n, ratio)


def test_p5a_large_dogs_get_big_bags_small_dogs_small_ones(products):
    customers = {c["customer_id"]: c for c in _load("customers.json")}
    customer_of_order = {o["order_id"]: o["customer_id"] for o in _load("orders.json")}
    big = defaultdict(lambda: [0, 0])    # pet_size → [lines of ≥ 7 kg, dog food lines]
    for ln in _load("order_lines.json"):
        p = products[ln["product_sku"]]
        if p["pet_type"] != "dog" or p["category"] not in ("dry-food", "wet-food"):
            continue
        size = customers[customer_of_order[ln["order_id"]]].get("pet_size")
        kg = pack_kg(p["name"])
        assert kg is not None, p["name"]
        big[size][0] += kg >= LARGE_PACK_KG
        big[size][1] += 1
    share = {size: b / n for size, (b, n) in big.items() if n}
    assert share["large"] / share["small"] >= 2.0, share
    assert SMALL_PACK_KG < LARGE_PACK_KG


def test_p6_every_row_links_to_its_months_state(states):
    month_of_order = {o["order_id"]: o["month"] for o in _load("orders.json")}
    rows = (
        [(r["product_state"], r["product_sku"], r["month"]) for r in _load("impressions.json")]
        + [(r["product_state"], r["product_sku"], month_of_order[r["order_id"]]) for r in _load("order_lines.json")]
        + [(r["product_state"], r["product_sku"], r["month"]) for r in _load("monthly_sales.json")]
    )
    wrong = [r for r in rows if r[0] not in states or r[0] != f"{r[1]}-{r[2]}"]
    assert not wrong, wrong[:5]
