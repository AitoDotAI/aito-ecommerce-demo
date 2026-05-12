"""Signal-validation tests for the PetNord fixtures.

These tests assert the engineered signal ranges from
`docs/adr/0002-data-model-and-fixtures.md`. Every demo moment in
`TASK.md` rests on at least one of these — if a signal drifts out
of band, a downstream view will silently lose its punchline.

The tests **read the on-disk JSON**, not the in-memory Python
output, so they catch regressions even if someone manually edits
`data/*.json` between regens.

Volume bands are wider than the targets in TASK.md because the
`_orders_per_customer` distribution is heavy-tailed and the seed
shouldn't bind us to one exact count. Signal targets are tighter
because *those* are the demo's load-bearing claims.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from data.generate_fixtures import (
    FILLABLE_CATEGORIES,
    PERSONAS,
)


DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _load(name: str) -> list[dict]:
    path = DATA_DIR / name
    if not path.exists():
        pytest.skip(f"{name} missing — run `./do generate-fixtures`.")
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def products() -> list[dict]:
    return _load("products.json")


@pytest.fixture(scope="module")
def customers() -> list[dict]:
    return _load("customers.json")


@pytest.fixture(scope="module")
def orders() -> list[dict]:
    return _load("orders.json")


@pytest.fixture(scope="module")
def order_lines() -> list[dict]:
    return _load("order_lines.json")


# ── Volume bands ───────────────────────────────────────────────────


def test_volumes_match_task_md_bands(products, customers, orders, order_lines):
    assert 600 <= len(products) <= 800, len(products)
    assert len(customers) == 3000, len(customers)
    # Orders is heavy-tailed — accept ±2k around the 14k target.
    assert 11_000 <= len(orders) <= 16_000, len(orders)
    assert 32_000 <= len(order_lines) <= 40_000, len(order_lines)


def test_link_targets_are_resolvable(products, customers, orders, order_lines):
    """Every order_line points at an existing order_id and product_sku;
    every order points at an existing customer_id. A broken link
    would tank Aito's `_recommend` / `_relate` joins silently."""
    customer_ids = {c["customer_id"] for c in customers}
    product_skus = {p["sku"] for p in products}
    order_ids = {o["order_id"] for o in orders}

    for o in orders:
        assert o["customer_id"] in customer_ids, o["order_id"]

    for ln in order_lines:
        assert ln["order_id"] in order_ids, ln["line_id"]
        assert ln["product_sku"] in product_skus, ln["line_id"]


# ── Signal #1: large-breed dog owners' cat-product share ───────────


def test_signal_1_large_breed_cat_share_under_one_percent(
    customers, products, orders, order_lines,
):
    sku_pet = {p["sku"]: p["pet_type"] for p in products}
    order_to_customer = {o["order_id"]: o["customer_id"] for o in orders}
    target_ids = {
        c["customer_id"] for c in customers
        if c.get("segment") == "dog_owner" and c.get("pet_size") == "large"
    }
    assert target_ids, "no large-breed dog owners — Smart Search demo can't run"

    n_total = 0
    n_cat = 0
    for ln in order_lines:
        if order_to_customer.get(ln["order_id"]) not in target_ids:
            continue
        n_total += 1
        if sku_pet[ln["product_sku"]] == "cat":
            n_cat += 1

    assert n_total > 0
    share = n_cat / n_total
    assert share < 0.01, f"cat share {share:.2%} ≥ 1% — Smart Search rank flip won't land"


# ── Signal #2: dog-food → dental-treats lift ───────────────────────


def test_signal_2_dog_food_dental_lift_at_least_2_5(
    products, orders, order_lines,
):
    sku_to_product = {p["sku"]: p for p in products}
    lines_by_order: dict[str, list[dict]] = {}
    for ln in order_lines:
        lines_by_order.setdefault(ln["order_id"], []).append(ln)

    n_orders = len(orders)
    n_with_dental = 0
    n_with_dryfood_dog = 0
    n_with_both = 0

    for o in orders:
        ols = lines_by_order.get(o["order_id"], [])
        has_dental = any(
            sku_to_product[ln["product_sku"]]["category"] == "dental-treats"
            for ln in ols
        )
        has_dryfood_dog = any(
            sku_to_product[ln["product_sku"]]["category"] == "dry-food"
            and sku_to_product[ln["product_sku"]]["pet_type"] == "dog"
            for ln in ols
        )
        if has_dental:
            n_with_dental += 1
        if has_dryfood_dog:
            n_with_dryfood_dog += 1
            if has_dental:
                n_with_both += 1

    assert n_orders > 0
    assert n_with_dryfood_dog > 0, "no dryfood-dog orders — generator is broken"

    p_dental = n_with_dental / n_orders
    p_dental_given = n_with_both / n_with_dryfood_dog
    lift = p_dental_given / p_dental if p_dental else 0
    assert lift >= 2.5, (
        f"dog-food→dental lift {lift:.2f}× < 2.5× — "
        f"Bought Together demo moment won't land"
    )


# ── Signal #3: persona top-5 (pet_type, category) overlap ──────────


def test_signal_3_maija_olli_top_pairs_disjoint_enough(
    products, orders, order_lines,
):
    """Maija (cat) and Olli (multi_pet, dog-leaning) should share ≤ 1
    of their top-5 (pet_type, category) pairs. If they share more,
    the For You customer-switcher won't visibly flip the grid."""
    sku_to_product = {p["sku"]: p for p in products}
    order_to_customer = {o["order_id"]: o["customer_id"] for o in orders}

    by_persona: dict[str, Counter[tuple[str, str]]] = {
        p.customer_id: Counter() for p in PERSONAS
    }
    for ln in order_lines:
        cid = order_to_customer.get(ln["order_id"])
        if cid in by_persona:
            prod = sku_to_product[ln["product_sku"]]
            by_persona[cid][(prod["pet_type"], prod["category"])] += 1

    maija_top = {pair for pair, _ in by_persona["CUST-00001"].most_common(5)}
    olli_top  = {pair for pair, _ in by_persona["CUST-00002"].most_common(5)}
    assert len(maija_top) == 5 and len(olli_top) == 5
    overlap = maija_top & olli_top
    assert len(overlap) <= 1, (
        f"Maija ∩ Olli top-5 overlap = {len(overlap)} pairs ({sorted(overlap)}); "
        f"For You differential won't be visible"
    )


# ── Signal #4: Filling-pile share ──────────────────────────────────


def test_signal_4_fillable_null_share_in_band(products):
    pool = [p for p in products if p["category"] in FILLABLE_CATEGORIES]
    assert pool, "no fillable products — Product Filling demo input pile is empty"
    n_nulled = sum(
        1 for p in pool
        if [p.get("weight_kg"), p.get("dietary"), p.get("tax_class")].count(None) >= 2
    )
    share = n_nulled / len(pool)
    assert 0.04 <= share <= 0.06, (
        f"fillable null share {share:.2%} outside 4–6 % band"
    )


# ── Signal #5: returned share ──────────────────────────────────────


def test_signal_5_returned_share_in_band(order_lines):
    n_returned = sum(1 for ln in order_lines if ln.get("returned"))
    share = n_returned / len(order_lines)
    assert 0.025 <= share <= 0.035, (
        f"returned share {share:.2%} outside 2.5–3.5 % band — "
        f"Evaluation honest-failure case may not be at the edge of "
        f"Aito's predictive ability"
    )


# ── Sanity ─────────────────────────────────────────────────────────


def test_personas_exist_with_stable_ids(customers):
    by_id = {c["customer_id"]: c for c in customers}
    for p in PERSONAS:
        assert p.customer_id in by_id, f"persona {p.name_hint} ({p.customer_id}) missing"
        actual = by_id[p.customer_id]
        assert actual["segment"] == p.segment, p.name_hint
        # `pet_size` is omitted from the JSON when None (the generator
        # strips Nones), so compare carefully.
        assert actual.get("pet_size") == p.pet_size, p.name_hint


def test_products_have_full_food_attributes_outside_filling_pile(products):
    """Most fillable-category products should have weight + dietary +
    tax_class set. The 5 % null share is the deliberate Filling pile."""
    pool = [p for p in products if p["category"] in FILLABLE_CATEGORIES]
    fully_populated = sum(
        1 for p in pool
        if p.get("weight_kg") is not None
        and p.get("dietary") is not None
        and p.get("tax_class") is not None
    )
    assert fully_populated / len(pool) >= 0.85, (
        "less than 85 % of fillable products carry all three attributes; "
        "Filling demo's 'most are populated, a few aren't' framing breaks"
    )


# ── Signal #6: Churn rate + driver presence ─────────────────────────


def test_signal_6_churn_rate_in_band(customers):
    """Overall churn rate should land in the 25-35% band.

    Outside that range the Churn view either looks empty (too low,
    the at-risk leaderboard runs out of unambiguously-risky candidates)
    or alarming (too high, the demo's "most customers stay" framing
    breaks). See ADR 0013."""
    n = len(customers)
    churned = sum(1 for c in customers if c.get("churned") is True)
    rate = churned / n
    assert 0.20 <= rate <= 0.38, (
        f"churn rate {rate:.1%} outside the 20-38 % demo band; "
        f"Churn view's narrative numbers won't land"
    )


def test_signal_6_personas_are_not_churned(customers):
    """The three persona customers (Maija / Olli / Saara) must stay
    active — they drive the For You demo and the Smart Search rank
    flip. If any persona is churned, those views lose their default
    state."""
    by_id = {c["customer_id"]: c for c in customers}
    for p in PERSONAS:
        c = by_id.get(p.customer_id)
        assert c is not None, f"persona {p.name_hint} missing"
        assert c.get("churned") is False, (
            f"persona {p.name_hint} ({p.customer_id}) is churned; "
            f"For You / Smart Search default state breaks"
        )


def test_signal_6_churn_drivers_are_learnable(customers):
    """At least one segment AND one region should have churn rate
    ≥ 1.3× baseline. The Churn view's drivers section filters at
    |lift - 1| ≥ 0.15, so 1.3× clears that comfortably. Without
    these driver values, the demo's "Aito surfaces the drivers"
    punchline doesn't land."""
    by_segment: dict[str, list[bool]] = {}
    by_region: dict[str, list[bool]] = {}
    for c in customers:
        by_segment.setdefault(c["segment"], []).append(c.get("churned") is True)
        by_region.setdefault(c["region"], []).append(c.get("churned") is True)
    baseline = sum(c.get("churned") is True for c in customers) / len(customers)

    def has_strong_driver(buckets: dict[str, list[bool]]) -> bool:
        for values in buckets.values():
            if len(values) < 30:
                continue   # too small a sample to count as a driver
            rate = sum(values) / len(values)
            if rate / baseline >= 1.3:
                return True
        return False

    assert has_strong_driver(by_segment), (
        "no segment has churn rate ≥ 1.3× baseline — Churn drivers will be empty"
    )
    assert has_strong_driver(by_region), (
        "no region has churn rate ≥ 1.3× baseline — Churn drivers will be empty"
    )


# ── Signal #7: Reviews fixture structure ────────────────────────────


def test_reviews_link_to_real_customers_and_products(customers, products):
    """Every review's customer_id and product_sku must resolve. This
    is a hard requirement for Aito link writes — a dangling link
    fails the loader."""
    reviews = _load("reviews.json")
    customer_ids = {c["customer_id"] for c in customers}
    skus = {p["sku"] for p in products}
    bad_cust = [r for r in reviews if r["customer_id"] not in customer_ids]
    bad_sku = [r for r in reviews if r["product_sku"] not in skus]
    assert not bad_cust, f"{len(bad_cust)} reviews have unknown customer_id"
    assert not bad_sku, f"{len(bad_sku)} reviews have unknown product_sku"


def test_reviews_categories_and_assignees_match(customers):
    """Every review must have one of the five valid categories, and
    the assigned_to must match the deterministic category→agent map.
    The Feedback view's confidence chips assume the mapping holds."""
    reviews = _load("reviews.json")
    valid_categories = {"shipping", "quality", "fit", "praise", "question"}
    expected_assignee = {
        "shipping": "Anna", "quality": "Petri", "fit": "Maria",
        "praise": "Joonas", "question": "Sari",
    }
    for r in reviews:
        assert r["category"] in valid_categories, r
        assert r["assigned_to"] == expected_assignee[r["category"]], r
        assert r["sentiment"] in {"positive", "negative", "neutral"}, r
        assert 1 <= r["rating"] <= 5, r


# ── Signal #8: Reviews carry forward churn label ────────────────────


def test_review_churn_within_90d_share_in_band():
    """`churn_within_90d` share across all reviews should land in
    8-18 %. Below that, the Feedback view's 4th predict has nothing
    to learn from; above that, the label correlates too strongly
    with category and the demo's "predict from text alone" framing
    weakens. See ADR 0013 §"Forward labels"."""
    reviews = _load("reviews.json")
    n_pos = sum(1 for r in reviews if r.get("churn_within_90d") is True)
    rate = n_pos / len(reviews) if reviews else 0
    assert 0.06 <= rate <= 0.20, (
        f"review churn_within_90d share {rate:.1%} outside the "
        f"6-20 % band — Feedback view's 4th predict won't read clean"
    )


def test_review_churn_label_correlates_with_customer_churn(customers):
    """Every review with `churn_within_90d=True` must belong to a
    customer who is themselves `churned=True`. The forward-looking
    label is a SUBSET of the customer's overall churn status —
    a review can be True only if the customer eventually stopped."""
    reviews = _load("reviews.json")
    by_id = {c["customer_id"]: c for c in customers}
    for r in reviews:
        if not r.get("churn_within_90d"):
            continue
        cust = by_id.get(r["customer_id"])
        assert cust is not None
        assert cust.get("churned") is True, (
            f"review {r['review_id']} has churn_within_90d=True but "
            f"customer {r['customer_id']} is not churned"
        )


# ── Signal #9: customer_months panel ────────────────────────────────


def test_customer_months_panel_volume(customers):
    """One row per customer per month they were a customer. Volume
    should land in 20k-35k for the 3000-customer fixture."""
    panel = _load("customer_months.json")
    assert 20000 <= len(panel) <= 35000, (
        f"customer_months count {len(panel)} outside 20k-35k band"
    )


def test_customer_months_every_customer_has_latest_row(customers):
    """Every customer must have a row at the cutoff month
    (2026-04). The Churn view's at-risk leaderboard filters on
    `month = 2026-04` and expects every active customer to appear."""
    panel = _load("customer_months.json")
    customers_in_panel_at_cutoff = {
        cm["customer_id"] for cm in panel if cm["month"] == "2026-04"
    }
    customers_with_orders = {
        c["customer_id"] for c in customers if c.get("total_orders", 0) > 0
    }
    missing = customers_with_orders - customers_in_panel_at_cutoff
    assert not missing, (
        f"{len(missing)} customers missing their 2026-04 row "
        f"(first 3: {list(missing)[:3]})"
    )


def test_customer_months_visit_decay_for_churned():
    """At the cutoff month (2026-04), active customers' visits
    should be substantially higher than churned customers'. The
    Churn view's at-risk predict relies on this gap as the
    strongest leading-indicator feature."""
    panel = _load("customer_months.json")
    cutoff_rows = [cm for cm in panel if cm["month"] == "2026-04"]
    active_visits = [
        cm["visits"] for cm in cutoff_rows
        if cm.get("churned_in_3_months") is False
    ]
    churned_visits = [
        cm["visits"] for cm in cutoff_rows
        if cm.get("churned_in_3_months") is True
    ]
    assert active_visits and churned_visits
    avg_active = sum(active_visits) / len(active_visits)
    avg_churned = sum(churned_visits) / len(churned_visits)
    assert avg_churned < avg_active * 0.5, (
        f"churned-customer visits {avg_churned:.1f} not low enough "
        f"vs active {avg_active:.1f} — visit-decay signal weak"
    )


def test_customer_months_label_consistent_with_customer_churn(customers):
    """For each customer, their customer_months rows' labels must
    match the rule: True iff customer.churned AND row.month ≥
    customer.last_order_month."""
    panel = _load("customer_months.json")
    by_id = {c["customer_id"]: c for c in customers}
    # Spot-check 100 random rows
    import random as _rnd
    rng = _rnd.Random(1)
    sample = rng.sample(panel, min(100, len(panel)))
    for cm in sample:
        cust = by_id.get(cm["customer_id"])
        assert cust is not None
        expected = bool(
            cust.get("churned")
            and cust.get("last_order_month") is not None
            and cm["month"] >= cust["last_order_month"]
        )
        actual = bool(cm.get("churned_in_3_months"))
        assert actual == expected, (
            f"label mismatch for {cm['customer_month_id']}: "
            f"expected {expected}, got {actual}"
        )
