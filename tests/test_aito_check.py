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
    "customer_id, expected_pet",
    [("CUST-00001", "cat"), ("CUST-00003", "dog")],   # Maija, Saara
)
def test_recommend_purchase_kpi_ranks_the_customers_own_pets_products(
    client, customer_id, expected_pet
):
    """`_recommend goal: {purchased: true}` with only the customer in the
    `where` returns a ranking whose top hits are for their pet: learned
    from their own rows, never handed a profile (ADR 0033)."""
    res = client.recommend(
        table="impressions",
        where={"context.customer": customer_id},
        recommend_field="product_sku",
        goal={"purchased": True},
        limit=5,
    )
    hits = res.get("hits", [])
    assert hits, f"empty recommendation for {customer_id}"
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
            where={"context.customer": "CUST-00001"},
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
            "context.customer": "CUST-00001",
            "product_sku.pet_type": "cat",
            "product_sku.category": "wet-food",
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


# ── Price: findings must be distinguishable from noise ───────────────


def test_price_view_flags_no_outlier_on_a_thin_history(client):
    """The view once opened on an "outlier" whose band came from two sales.
    Every flagged outlier must have enough observations for a band, and
    every sweet spot must have support and a lift interval excluding 1."""
    from src.price_bands import MIN_OUTLIER_OBSERVATIONS, MIN_SWEET_SPOT_SUPPORT
    from src.price_service import get_prices
    from src import cache

    cache.clear()
    response = get_prices(client)
    thin = [b.sku for b in response.fair_bands if b.outlier and b.observation_count < MIN_OUTLIER_OBSERVATIONS]
    assert not thin, f"outliers on a thin history: {thin}"
    weak = [s.category for s in response.sweet_spots if s.f_on_condition < MIN_SWEET_SPOT_SUPPORT]
    assert not weak, f"sweet spots on thin support: {weak}"


# ── Churn: profile drivers, one row per customer (ADR 0013 amendment) ─


def test_relate_over_churned_customers_counts_match_a_search(client):
    """`_relate` with churn as `where`: a value's counts must be the plain
    `_search` counts of that value among churners (`fOnCondition`) and among
    everyone (`f`), so the `where` is known to act as the condition."""
    from src.aito_compat import related_value
    from src.churn_drivers import CHURNED

    # `pets` is the declared Text column (ADR 0033): one hit per word.
    hits = client.relate(table="customers", where=CHURNED, relate_field="pets", limit=20)["hits"]
    aquarium = next(h for h in hits if related_value(h, "pets") == "aquarium")

    def count(where: dict) -> int:
        return client.search("customers", where=where, limit=0)["total"]

    has_aquarium = {"pets": {"$match": "aquarium"}}
    assert aquarium["fs"]["fOnCondition"] == count({**CHURNED, **has_aquarium})
    assert aquarium["fs"]["f"] == count(has_aquarium)


def test_churn_profile_drivers_name_long_tenure_and_skip_reviews(client):
    """The drivers list is non-empty, long tenure raises churn and short
    tenure lowers it (the generator's tenure effect), and no review-derived
    field appears: those read backwards on this data (ADR 0013)."""
    from src.churn_drivers import get_churn_drivers

    result = get_churn_drivers(client)

    assert result.drivers, "no churn drivers on the loaded data"
    tenure = {d.value: d.lift for d in result.drivers if d.field == "tenure"}
    assert tenure.get("18 months or more", 0) > 1.15, tenure
    assert tenure.get("under 6 months", 2) < 0.85, tenure
    assert not any(d.field.startswith("latest_") for d in result.drivers)


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


# ── Product Insights: one product's funnel and buyers (ADR 0028) ─────


def test_product_insights_funnel_is_monotone_and_relate_counts_its_lines(client):
    """For the default product: the funnel never grows step to step, the
    surfaces cover every impression (the service asserts that), and the
    "who buys it" `_relate` conditions on exactly this product's order
    lines (`fCondition` equals a plain count)."""
    from src.product_insights_service import DEFAULT_SKU, get_product_insights

    result = get_product_insights(client, DEFAULT_SKU)

    counts = [step.count for step in result.funnel]
    assert counts[0] > 0, "no impressions for the default product"
    assert counts == sorted(counts, reverse=True), counts
    lines = client.search("order_lines", where={"product_sku": DEFAULT_SKU}, limit=0)["total"]
    assert result.buyers, "no buyer profiles for the default product"
    assert all(b.lines_total == lines for b in result.buyers), (lines, result.buyers[:2])
    assert result.monthly, "no monthly_sales rows for the default product"


# ── v2 engine behaviour the views rely on (checked on 2.11.4) ────────


def test_recommend_where_on_a_linked_product_field_filters_the_candidates(client):
    """On v2, a `where` on the candidate's own fields was reported to stop
    filtering `_recommend` candidates (aito-shopify notes). For You relies
    on it filtering, so every candidate must be a cat product here."""
    hits = client.recommend(
        "impressions", {"product_sku.pet_type": "cat"}, "product_sku", {"purchased": True}, limit=10,
    )["hits"]

    assert hits, "no recommendations for cat products"
    assert all(h["pet_type"] == "cat" for h in hits), [h.get("pet_type") for h in hits]


def test_match_on_a_text_column_matches_a_token_not_the_whole_value(client):
    """`$match` must keep token semantics on v2 tables: an order whose
    categories are "dog_wetfood cat_litter" matches "dog_wetfood". If it fell
    back to whole-value equality the two counts would be equal."""
    token = client.search("orders", where={"line_categories": {"$match": "dog_wetfood"}}, limit=0)["total"]
    whole_value = client.search("orders", where={"line_categories": "dog_wetfood"}, limit=0)["total"]

    assert token > whole_value > 0, (token, whole_value)


# ── Price what-if: the regression model's why (ADR 0029) ─────────────


def test_price_what_if_explains_the_estimate_with_price_as_a_factor(client):
    """The waterfall's rows multiply out to the estimate (`waterfall` raises
    otherwise), price is one of them, and the what-if agrees with the demand
    curve's point at the same price, since both ask the regression model."""
    from src.price_service import get_price_detail
    from src.price_what_if import get_price_what_if

    detail = get_price_detail(client, "SKU-PT-0133")
    centre = next(p for p in detail.curve if p.adjustment_pct == 0)

    what_if = get_price_what_if(client, "SKU-PT-0133", centre.price_eur)

    assert what_if.units >= 0
    assert "price_eur" in {f.field for f in what_if.factors}, what_if.factors
    assert what_if.units == centre.units_sold, (what_if.units, centre.units_sold)


# ── ADR 0030: shoppers with a story (docs/verification/shoppers-data-prereg.md) ──


def _keeps_grain_free(hit: dict) -> bool:
    """A recommended product keeps a grain-free household's rule when it
    is grain-free, or isn't dog or cat food at all (S1 covers food only)."""
    food = hit.get("category") in ("dry-food", "wet-food") and hit.get("pet_type") in ("dog", "cat")
    return not food or "Grain Free" in hit["name"]


@pytest.mark.xfail(strict=True, reason=(
    "Pre-registered A1 failed on 2026-10-13 (shoppers-data-prereg.md): rule households "
    "made 14 purchases, too few for _recommend to learn a rule. The Shop applies the rule "
    "as a filter instead (ADR 0031). Strict: if this starts passing, say so."))
def test_a1_recommend_keeps_a_grain_free_households_rule(client):
    """A1: with the rule in the `where`, ≥ 9 of the top 10 keep it; the same
    query without the rule keeps it ≤ 7 times."""
    # `product_sku.category` filters the candidates; the impression's own
    # `product_category` would only be context (first run, 2026-10-12).
    # ADR 0033: the declared diet and pets, through the context's customer.
    household = {"context.customer.pets": {"$match": "dog"}, "context.customer.diet": "grain-free",
                 "product_sku.category": "dry-food"}
    without_rule = {k: v for k, v in household.items() if k != "context.customer.diet"}

    def kept(where: dict) -> int:
        hits = client.recommend("impressions", where, "product_sku", {"purchased": True}, limit=10)["hits"]
        assert len(hits) == 10, hits
        return sum(map(_keeps_grain_free, hits))

    assert kept(household) >= 9, kept(household)
    assert kept(without_rule) <= 7, kept(without_rule)


def _relate_interval(client, table: str, where: dict, field: str, value: str) -> tuple[float, float]:
    from src.aito_compat import related_value
    from src.price_bands import lift_interval

    hits = client.relate(table=table, where=where, relate_field=field, limit=50)["hits"]
    hit = next(h for h in hits if related_value(h, field) == value)
    fs = hit["fs"]
    return lift_interval(float(hit["lift"]), fs["fOnCondition"], fs["fCondition"], fs["f"], fs["n"])


DECEMBERS = ["2024-12", "2025-12"]
SUMMERS = ["2024-06", "2024-07", "2024-08", "2025-06", "2025-07", "2025-08"]


@pytest.mark.parametrize("months, category", [(DECEMBERS, "treats"), (DECEMBERS, "toys"), (SUMMERS, "grooming")])
def test_a4_the_season_lifts_its_categories(client, months, category):
    """A4: the planted month × category cells have a lift whose 95 % interval
    sits above 1. Related over order lines, which count what was bought;
    monthly_sales has one row per SKU and month whatever it sold, so a
    category's share of its rows can't move with the season."""
    low, _ = _relate_interval(client, "order_lines", {"order_id.month": {"$or": months}},
                              "product_sku.category", category)
    assert low > 1, (months[0], category, low)


def test_a5_the_lowest_rated_products_are_bought_less(client):
    """A5: among purchased impressions, the 1–2 star band's lift has its
    95 % interval below 1."""
    _, high = _relate_interval(client, "impressions", {"purchased": True}, "product_sku.rating_band", "1-2")
    assert high < 1, high


# ── Shop (ADR 0031), on ADR 0030's data ─────────────────────────────


def test_shop_grid_for_a_grain_free_household_holds_no_rule_breaking_food(client):
    from src.shop_grid import get_shop_grid

    grid = get_shop_grid(client, "janne", "2026-04", [])

    assert grid.rule == "grain-free" and grid.items
    food = [i for i in grid.items if i.category in ("dry-food", "wet-food")]
    assert all("Grain Free" in i.name for i in food), [i.name for i in food]


def test_shop_a_cage_in_the_cart_changes_what_is_recommended(client):
    """A6's shop form: the cart is context, so the ranking moves with it."""
    from src.shop_grid import get_shop_grid

    empty = [i.sku for i in get_shop_grid(client, "paivi", "2026-04", []).items[:5]]
    with_cage = [i.sku for i in get_shop_grid(client, "paivi", "2026-04", ["SKU-PT-0555"]).items[:5]]

    assert empty != with_cage, empty


def test_shop_an_item_bought_last_order_scores_lower_as_just_bought(client):
    """A8's shop form: re-asked with just_bought: true, a product's purchase
    probability drops below what it was before the shopper bought it."""
    from src.shop_context import shopper_where

    context = shopper_where("CUST-00053", [], "2026-04", [])
    sku = "SKU-PT-0278"   # in Helena's last order

    def p(extra: dict) -> float:
        hits = client._request("POST", "/_predict", json={
            "from": "impressions", "where": {**context, "product_sku": sku, **extra}, "predict": "purchased"})["hits"]
        return next(h["$p"] for h in hits if h.get("feature", h.get("$value")) is True)

    assert p({"just_bought": True}) < p({})


def test_shop_suggests_the_hideout_next_for_a_cage_and_a_bottle(client):
    """A2's shop form, for Päivi as of April 2026: she owns a cage and a
    bottle, and the kit's next item is the hideout."""
    from src.shop_suggestions import get_suggestions

    result = get_suggestions(client, "paivi", "2026-04")

    assert result.owned == {"small_animal": ["cage", "water_bottle"]}, result.owned
    assert result.next_for_pet and "Hideout" in result.next_for_pet[0].name, result.next_for_pet
    assert result.usual, "no usual basket for a shopper with orders"
def test_r5_a_new_owner_with_a_cage_in_the_cart_is_shown_the_bottle(client):
    """R5 (observable-data-prereg.md): Päivi as of February 2026, before her
    first order, owns nothing; with a cage in the cart, the kit's next item
    (the water bottle) is in the grid's top 3, with the cart among its reasons."""
    from src.shop_grid import get_shop_grid

    grid = get_shop_grid(client, "paivi", "2026-02", ["SKU-PT-0555"])

    top3 = grid.items[:3]
    bottles = [i for i in top3 if "Water Bottle" in i.name]
    assert bottles, [i.name for i in grid.items]
    assert any(r.label == "Goes with your cart" for r in bottles[0].reasons), bottles[0].reasons


def test_r5_an_owner_of_cage_and_bottle_is_shown_an_add_on_not_another_cage(client):
    """R5, as amended: Päivi as of April 2026 owns a cage and a bottle; with an
    empty cart, an add-on she lacks is in the top 3 and no cage in the top 12."""
    from src.shop_grid import get_shop_grid

    grid = get_shop_grid(client, "paivi", "2026-04", [])

    names = [i.name for i in grid.items]
    # Amended (observable-data-prereg.md): an add-on she lacks, not the hideout specifically.
    assert any(k in n for n in names[:3] for k in ("Hideout", "Exercise Wheel", "Tunnel")), names
    assert not any(n.endswith("Cage") for n in names), names


def test_shop_search_keeps_the_household_rule(client):
    """Search ranks through `_recommend`, which applies the rule; `_search …
    get` would not (it returned grain food for this household, 2026-10-17)."""
    from src.shop_search import search_shop

    found = search_shop(client, "janne", "2026-04", [], "food")

    assert found.text_matched and found.items
    # The rule covers dog and cat food (ADR 0030), as the filter does.
    assert all("Grain Free" in i.name for i in found.items
               if i.category in ("dry-food", "wet-food") and i.pet_type in ("dog", "cat")), \
        [i.name for i in found.items]


def test_shop_search_for_words_no_name_holds_returns_nothing(client):
    from src.shop_search import search_shop

    found = search_shop(client, "paivi", "2026-04", [], "zzqx")

    assert (found.text_matched, found.items) == (False, [])


def test_shop_alternatives_are_the_same_kind_for_the_same_pet(client):
    from src.shop_product import get_product_drawer

    drawer = get_product_drawer(client, "SKU-PT-0182", "janne", "2026-04", [])

    assert drawer.alternatives
    assert all((a.category, a.pet_type) == ("dental-treats", "dog") and a.sku != "SKU-PT-0182"
               for a in drawer.alternatives), drawer.alternatives


# ── Shop analytics (ADR 0031): each section shows rows and a planted pattern ──
# Rows are judged with clustering by customer and a Bonferroni level per
# section (src/lift_rows.py), so a planted effect on few customers can
# fall short: just-bought products under purchases (40 purchases, about 20
# independent) and summer grooming (157 lines, about 28) do, on 2026-10-13.


@pytest.fixture(scope="module")
def shop_analytics(client):
    from src.basket_pairs import get_basket_section
    from src.search_words import get_search_words_section
    from src.shop_analytics_service import get_funnel_section, get_who_section

    return {
        "purchased": get_funnel_section(client, "purchased"),
        "clicked": get_funnel_section(client, "clicked"),
        "summer": get_who_section(client, "summer"),
        "grain-free": get_who_section(client, "grain-free"),
        "baskets": get_basket_section(client),
        "words": get_search_words_section(client),
    }


def _row(rows, field, value):
    return next((r for r in rows if (r.field, r.value) == (field, value)), None)


def test_shop_analytics_shown_rows_clear_1_and_rest_on_30_independent_rows(shop_analytics):
    for name in ("purchased", "clicked", "summer", "grain-free"):
        section = shop_analytics[name]
        assert section.clustering.design_effect >= 1, name
        for r in section.rows:
            assert r.interval_low > 1 or r.interval_high < 1, (name, r)
            assert r.rows_with_value / section.clustering.design_effect >= 30, (name, r)
    pairs = shop_analytics["baskets"].pairs
    assert pairs and all(p.interval_low > 1 or p.interval_high < 1 for p in pairs)


def test_shop_analytics_low_rated_products_sell_less(shop_analytics):
    """S5: the 1–2 star band is under-represented among purchases."""
    row = _row(shop_analytics["purchased"].rows, "product_sku.rating_band", "1-2")
    assert row and row.interval_high < 1, row


def test_shop_analytics_just_bought_products_are_clicked_less(shop_analytics):
    """S8: a product in the last order draws fewer clicks (109 of 24,950)."""
    row = _row(shop_analytics["clicked"].rows, "just_bought", "true")
    assert row and row.interval_high < 1, row


def test_shop_analytics_summer_sells_health(shop_analytics):
    """S4: health is bought more in June–August."""
    row = _row(shop_analytics["summer"].rows, "product_sku.category", "health")
    assert row and row.interval_low > 1, row


def test_shop_analytics_a_grain_free_household_buys_grain_free_food(shop_analytics):
    """S1: the rule shows in what the household buys, even counting each
    household as one cluster (design effect ≈ 20 lines)."""
    row = _row(shop_analytics["grain-free"].rows, "product_sku.dietary", "grain-free")
    assert row and row.interval_low > 1, row


def test_shop_analytics_dog_dry_food_goes_with_dental_treats(shop_analytics):
    """The engineered basket complement (ADR 0002), at category level."""
    pairs = {(p.first, p.second): p for p in shop_analytics["baskets"].pairs}
    pair = pairs.get(("Dog dry-food", "Dog dental-treats"))
    assert pair and pair.interval_low > 1, sorted(pairs)


def test_shop_analytics_search_words_against_the_search_average(client, shop_analytics):
    """Some words convert above the search average. The lift is against
    search impressions, which is right only if no other surface carries a
    query: check that."""
    words = shop_analytics["words"]
    assert any(w.lift > 1 for w in words.rows), words.rows
    assert words.significance.tested <= words.words
    anywhere = client.search("impressions", where={"context.search_query": {"$match": "food"}}, limit=0)["total"]
    on_search = client.search("impressions", where={"context.surface": "search",
                                                    "context.search_query": {"$match": "food"}}, limit=0)["total"]
    assert anywhere == on_search > 0, (anywhere, on_search)
