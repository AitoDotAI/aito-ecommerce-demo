"""Live Aito query sanity checks — `./do aito-check`.

Unlike `test_aito_methods.py` (offline body-shape asserts), these run
the demo's query patterns against the loaded PoC dataset and assert the
response *behaves*: probabilities in range, rankings non-empty for
known-good inputs, invariants hold. Per CLAUDE.md §"Aito query sanity",
every new query pattern lands a check here in the same PR.

Skipped automatically when the instance isn't reachable (offline CI),
so `./do test` stays green without a live DB.
"""

from __future__ import annotations

import pytest

from src.aito_client import AitoClient
from src.config import load_config


@pytest.fixture(scope="module")
def client() -> AitoClient:
    cfg = load_config()
    c = AitoClient(cfg)
    if not c.check_connectivity():
        pytest.skip(f"Aito not reachable at {cfg.aito_api_url}")
    return c


def _count(client: AitoClient, where: dict) -> int:
    """Row count for a where-filter on the impressions table."""
    res = client._request(
        "POST", "/_query", json={"from": "impressions", "where": where, "limit": 0}
    )
    return res["total"]


# ── Impressions: the recommendation conversion KPI (ADR 0021) ────────


@pytest.mark.parametrize(
    "segment, expected_pet",
    [("cat_owner", "cat"), ("dog_owner", "dog")],
)
def test_recommend_purchase_kpi_ranks_segment_appropriate_products(
    client, segment, expected_pet
):
    """`_recommend goal: {purchased: true}` returns a non-empty ranking
    whose top hits match the segment's pet — the persona flip, learned
    from the funnel rather than asserted."""
    res = client.recommend(
        table="impressions",
        where={"customer_segment": segment},
        recommend_field="product_sku",
        goal={"purchased": True},
        limit=5,
    )
    hits = res.get("hits", [])
    assert hits, f"empty recommendation for {segment}"
    for hit in hits:
        assert 0.0 <= hit["$p"] <= 1.0, hit["$p"]
    top_pets = [h.get("pet_type") for h in hits[:3]]
    assert all(pet == expected_pet for pet in top_pets), top_pets


# ── Smart Search: BM25 left, P(purchase) x BM25 right (ADR 0026) ─────


def _blend(client, query: str, persona_id: str) -> list[dict]:
    from src.search_service import PERSONAS, predictive_blend_body

    body = predictive_blend_body(query, PERSONAS[persona_id], limit=10)
    return client.search(table=body["from"], get=body["get"], where=body["where"],
                         order_by=body["orderBy"], select=body["select"],
                         limit=body["limit"])["hits"]


def test_smart_search_food_flips_between_cat_and_dog_owner(client):
    """The demo's headline: same query, different customer, different
    products. Without a candidate filter the flip must come from `$p`;
    if persona context stopped conditioning `$p` in the `get` form, both
    columns would show the same list."""
    maija = [h["pet_type"] for h in _blend(client, "food", "maija")[:5]]
    saara = [h["pet_type"] for h in _blend(client, "food", "saara")[:5]]
    assert maija == ["cat"] * 5, maija
    assert saara == ["dog"] * 5, saara


@pytest.mark.parametrize("persona_id, query, expected_pet", [
    ("maija", "cat food", "cat"),
    ("saara", "dog food", "dog"),
    ("olli", "dog food", "dog"),    # the thin dog_owner + small slice
    # The text must beat purchase history: a cat owner asking for dog
    # food gets dog food. At Aito's default text weight (θ 0.33) she got
    # cat food; this pins the reason TEXT_THETA is higher.
    ("maija", "dog food", "dog"),
])
def test_smart_search_predictive_column_stays_on_the_asked_for_pet(
    client, persona_id, query, expected_pet
):
    off_pet = [h["name"] for h in _blend(client, query, persona_id)
               if h["pet_type"] != expected_pet]
    assert not off_pet, f"{persona_id} / {query!r} leaked: {off_pet}"


def test_smart_search_baseline_returns_nothing_when_no_word_matches(client):
    """BM25 ties every row at lift 1.0 when no query word matches, and the
    tie comes back in table order (dog dry food first). The baseline must
    show nothing then, not ten products that merely come first."""
    from src.search_service import _baseline_search

    assert _baseline_search(client, "hundmat", 10) == []
    assert _baseline_search(client, "dog food", 10), "a matching query must still return rows"


def test_recommend_clicks_and_purchases_goals_differ(client):
    """The demo beat: ranking by engagement (clicked) is not the same as
    ranking by conversion (purchased)."""
    def top_skus(goal_field: str) -> list[str]:
        res = client.recommend(
            table="impressions",
            where={"customer_segment": "cat_owner"},
            recommend_field="product_sku",
            goal={goal_field: True},
            limit=10,
        )
        return [h["sku"] for h in res.get("hits", [])]

    clicked = top_skus("clicked")
    purchased = top_skus("purchased")
    assert clicked and purchased
    assert clicked != purchased, "click-goal and purchase-goal rankings are identical"


def test_predict_purchased_returns_both_classes(client):
    """`_predict purchased` gives a calibrated true/false split, both in
    [0, 1] and summing to ~1."""
    res = client.predict(
        table="impressions",
        where={
            "customer_segment": "cat_owner",
            "product_pet_type": "cat",
            "product_category": "wet-food",
        },
        predict_field="purchased",
    )
    by_feature = {h["feature"]: h["$p"] for h in res.get("hits", [])}
    assert True in by_feature and False in by_feature, by_feature
    assert all(0.0 <= p <= 1.0 for p in by_feature.values())
    assert abs(sum(by_feature.values()) - 1.0) < 0.05


def test_impression_funnel_is_monotone(client):
    """purchased ⇒ added_to_cart ⇒ clicked must hold in aggregate:
    each step of the funnel can only shrink."""
    clicked = _count(client, {"clicked": True})
    carted = _count(client, {"added_to_cart": True})
    purchased = _count(client, {"purchased": True})
    assert clicked >= carted >= purchased > 0, (clicked, carted, purchased)
    # A cart without a click, or a purchase without a cart, would be a
    # generation bug — assert the impossible rows are truly absent.
    assert _count(client, {"clicked": False, "added_to_cart": True}) == 0
    assert _count(client, {"added_to_cart": False, "purchased": True}) == 0


# ── Basket rule mining — order-level _relate sweep (ADR 0022) ─────────


def test_basket_rules_mines_well_formed_association_rules(client):
    """The Basket Rules sweep returns non-empty, well-formed rules:
    confidence in [0,1], support in [0,1] (order-granular — never the
    >100% the line-granular link-traversal shape produced), lift > 1,
    and the canonical dog dry-food → dental-treats rule is present."""
    from src.basket_rules_service import get_basket_rules

    resp = get_basket_rules(client)
    assert resp.rules, "no basket rules mined"
    for r in resp.rules:
        assert 0.0 <= r.confidence <= 1.0, r
        assert 0.0 <= r.support_pct <= 1.0, r           # order-granular, never >1
        assert r.lift > 1.0, r                          # positive association only
        assert r.support_orders >= 50, r                # absolute-count gate held
    pairs = {(r.antecedent, r.consequent) for r in resp.rules}
    assert ("Dog dry-food", "Dog dental-treats") in pairs, sorted(pairs)


# ── Instance health: are the tables actually optimized? ──────────────


def test_table_counts_return_fast_enough_to_serve(client):
    """A bare `limit: 0` count must be quick on every table.

    This is a health probe, not a performance benchmark. Batch uploads
    leave one segment per batch, and a table left unmerged answers a
    plain count in 3-20 s instead of ~0.3 s. That is not a slow demo, it
    is a broken one: `_kpi_counts` issues several of these per dashboard
    request and once exceeded the 90 s client timeout, so /api/dashboard
    answered 500 with no hint that segmentation was the cause.

    The threshold is deliberately loose — an order of magnitude above a
    healthy instance (~0.2-0.5 s) and well under the pathology — so this
    fails when a load was interrupted, not when the shared instance is
    merely busy. If it trips, run `./do optimize`.
    """
    import time

    from src.schema import SCHEMAS

    budget_s = 5.0
    slow: list[tuple[str, float]] = []
    for table in SCHEMAS:
        started = time.perf_counter()
        client._request("POST", "/_search", json={"from": table, "limit": 0})
        elapsed = time.perf_counter() - started
        if elapsed > budget_s:
            slow.append((table, elapsed))

    assert not slow, (
        "table(s) answering a bare count too slowly — most likely left in "
        "many unmerged segments by an interrupted load; run `./do optimize`: "
        + ", ".join(f"{t} {e:.1f}s" for t, e in slow)
    )


# ── Evaluation: the hold-out must represent the population ───────────


def test_evaluate_baseline_matches_the_population_majority_share(client):
    """A representative hold-out gives a majority-class baseline close to
    the population's majority share. `products.pet_type` is 278/658 = 0.42
    cat, so the baseline must land near that.

    This is what caught the bug: a first-200 `testSource.limit` took the
    head of a table grouped by type, no test row carried the majority
    class, and the baseline read 0.0 — making a working model look like
    one scoring 0.06. With a seeded `$sample` it is ~0.40 and the model
    ~0.85. Bounds are wide on purpose (a 200-row sample of 658 varies);
    they exclude the failure, not the noise.
    """
    from src.eval_service import MODELS

    m = next(m for m in MODELS if m.predict == "pet_type")
    res = client.evaluate(m.table, m.where, m.predict)
    base, acc = res["baseAccuracy"], res["accuracy"]
    assert 0.30 <= base <= 0.55, f"baseline {base} is not the ~0.42 majority share"
    assert acc - base >= 0.2, f"model {acc} barely beats its baseline {base}"


# ── Demand: a time-split `_evaluate` (ADR 0014 §Correction) ──────────


def test_demand_time_split_tests_exactly_the_latest_month(client):
    """`test: {month: latest}` must hold out that month's rows and nothing
    else, and the naive score must be read from the same rows — otherwise
    the model and naive numbers on the page are not comparable."""
    from src.demand_evaluation import evaluate_demand
    from src.demand_forecast import LATEST_MONTH

    rows = client.search("monthly_sales", where={"month": LATEST_MONTH}, limit=0)["total"]
    e = evaluate_demand(client, LATEST_MONTH)
    assert e.n == rows > 0
    for name, value in (("model", e.accuracy), ("naive", e.naive_accuracy),
                        ("majority", e.base_accuracy)):
        assert 0.0 <= value <= 1.0, f"{name} accuracy {value} is not a share"


def test_demand_time_split_honours_the_train_proposition(client):
    """If `train` were ignored the model could learn from the month it is
    tested on. Training on the oldest month alone must change the score
    on the same test rows; if it does not, `train` is not being read."""
    from src.demand_evaluation import _FEATURES
    from src.demand_forecast import LATEST_MONTH

    def accuracy(train: dict) -> float:
        return client.evaluate(
            "monthly_sales", {f: {"$get": f} for f in _FEATURES}, "units_bucket",
            train=train, test={"month": LATEST_MONTH})["accuracy"]

    everything_before = accuracy({"month": {"$not": LATEST_MONTH}})
    oldest_only = accuracy({"month": "2024-05"})
    assert everything_before != oldest_only
