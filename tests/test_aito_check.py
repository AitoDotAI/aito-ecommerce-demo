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

import math
import os

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


def test_supply_flags_no_price_outlier_on_a_thin_history(client):
    """Price once opened on an "outlier" whose band came from two sales.
    Over the realised prices Supply reads, every flagged outlier must rest on
    enough observations for a band to mean anything."""
    from src.catalogue_reads import products_by_sku, read_all, rows_by_sku
    from src.price_bands import MIN_OUTLIER_OBSERVATIONS, price_band

    products = products_by_sku(client)
    bands = [price_band([float(r["price_eur"]) for r in rows], float(products[sku]["price_eur"]))
             for sku, rows in rows_by_sku(read_all(client, "product_states")).items()]
    assert any(b.outlier for b in bands), "no outlier at all: is the band rule reading the prices?"
    assert not [b for b in bands if b.outlier and b.observations < MIN_OUTLIER_OBSERVATIONS]


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


# ── Retention: the churn score's population, and the win-back offer ──


def test_churn_population_is_the_orders_whose_follow_up_is_known(client):
    """The nested `from` must restrict the rows Aito learns from: a String
    month compares with `$lte`, so the population is exactly the months up
    to LABEL_KNOWN_UNTIL in which the customer ordered, and both answers
    occur in it."""
    from src.churn_risk import POPULATION

    where = POPULATION["where"]
    rows = client.search("customer_months", where=where, limit=0)["total"]
    leavers = client.search("customer_months", where={**where, "churned_in_3_months": True}, limit=0)["total"]
    later = client.search("customer_months", where={"$and": [where, {"month": {"$gt": "2026-01"}}]},
                          limit=0)["total"]
    assert rows > 0 and 0 < leavers < rows
    assert later == 0


def test_batched_churn_predicts_over_the_population_return_both_answers(client):
    """`_batch` accepts a `_predict` with a nested `from`; each answer has a
    true and a false hit whose probabilities sum to 1."""
    from src.churn_risk import evidence_of, predict_body

    rows = client.search("customer_months", where={"month": "2026-04", "purchases": {"$gte": 1}},
                         limit=3)["hits"]
    answers = client.batch([predict_body(evidence_of(r), with_why=False) for r in rows])
    assert len(answers) == len(rows)
    for answer in answers:
        p = {h["feature"]: h["$p"] for h in answer["hits"]}
        assert set(p) == {True, False} and abs(sum(p.values()) - 1) < 1e-6


def test_churn_time_split_tests_every_order_of_the_latest_known_month(client):
    """Evidence's churn check holds out exactly the orders of the test month,
    and the score beats always answering "another order follows"."""
    from src.churn_evaluation import evaluate_churn
    from src.churn_risk import LABEL_KNOWN_UNTIL

    rows = client.search("customer_months", where={"month": LABEL_KNOWN_UNTIL, "purchases": {"$gte": 1}},
                         limit=0)["total"]
    check = evaluate_churn(client)
    assert check.n == rows > 0
    assert check.accuracy > check.base_accuracy


def test_a_batched_recommend_hit_is_only_p_and_value(client):
    """Unlike a direct `_recommend`, a `_batch` item's hit carries no linked
    product columns, so the offer reads the SKU from `$value`."""
    from src.winback_offer import customer_where, recommend_body

    [answer] = client.batch([recommend_body(customer_where("CUST-00008", "none"), ["small_animal"])])
    assert answer["hits"] and set(answer["hits"][0]) == {"$p", "$value"}


def test_winback_response_predictions_match_the_observed_response_rate(client):
    """`_predict responded` is the rate the offer shows, so it must be a rate:
    averaged over past sends, it lands near the share that responded."""
    sends = client.search("winback_campaigns", limit=200)["hits"]
    answers = client.batch([{"from": "winback_campaigns", "limit": 2, "select": ["$p", "feature"],
                             "predict": "responded",
                             "where": {k: s[k] for k in ("customer_id", "customer_staple_category",
                                                         "recency_bucket", "product_sku")}}
                            for s in sends])
    predicted = sum(next(h["$p"] for h in a["hits"] if h["feature"] is True) for a in answers) / len(sends)
    observed = sum(s["responded"] for s in sends) / len(sends)
    assert abs(predicted - observed) < 0.1, (predicted, observed)


def test_an_estimate_is_not_a_batch_item(client):
    """`_batch` refuses `estimate` (400 "unexpected field"), so the offers'
    order values are separate `_estimate` calls."""
    from src.aito_client import AitoError

    with pytest.raises(AitoError, match="estimate"):
        client.batch([{"from": "winback_campaigns", "where": {"responded": True}, "estimate": "order_value_eur"}])


# ── Supply: the markdown sweep ───────────────────────────────────────


def test_the_markdown_sweep_estimates_more_units_at_a_lower_price(client):
    """The regression `_estimate` the markdown sweep asks must not sell less
    at a deeper discount, or "the shallowest level that clears" is noise."""
    from src.catalogue_reads import read_all
    from src.demand_forecast import last_month_units, units_at_price

    sales = read_all(client, "monthly_sales", where={"product_sku": "SKU-PT-0496"})
    profile = max(sales, key=lambda r: r["month"])
    units = [units_at_price(client, "SKU-PT-0496", profile, last_month_units(sales), price, model="regression")
             for price in (20.29, 16.23)]     # list price, and 20 % off
    assert units[1] >= units[0] > 0, units


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


# ── Product: history, buyers and the decision (ADR 0028, ADR 0041) ───


def test_product_history_batch_returns_counts_and_every_row(client):
    """For the default product: the funnel never grows step to step, the
    surfaces cover every impression (the service asserts that), and the
    rows in the same `_batch` come back whole (`total` equals the hits:
    `_rows` asserts it), one month per state."""
    from src.product_history import get_product_history
    from src.product_service import DEFAULT_SKU

    history = get_product_history(client, DEFAULT_SKU)

    counts = [step.count for step in history.funnel]
    assert counts[0] > 0, "no impressions for the default product"
    assert counts == sorted(counts, reverse=True), counts
    assert len(history.months) == 24, [m.month for m in history.months]
    assert sum(m.units_sold for m in history.months) > 0
    assert sum(history.ratings.values()) == sum(history.sentiments.values()) > 0


def test_product_buyers_relate_counts_exactly_the_products_order_lines(client):
    """The "who buys it" `_relate` conditions on exactly this product's
    order lines: `fCondition` equals a plain count."""
    from src.product_buyers import get_buyers
    from src.product_service import DEFAULT_SKU

    buyers = get_buyers(client, DEFAULT_SKU)

    lines = client.search("order_lines", where={"product_sku": DEFAULT_SKU}, limit=0)["total"]
    assert buyers, "no buyer profiles for the default product"
    assert all(b.lines_total == lines for b in buyers), (lines, buyers[:2])


def test_product_view_leads_with_a_decision_in_range(client):
    """The decision's rates are Aito's `$p` in [0, 1], its margins follow
    from them, and the price what-if answers at today's price and, when
    the advice changes the band, at the advised price."""
    from src.product_service import DEFAULT_SKU, get_product_view

    view = get_product_view(client, DEFAULT_SKU)

    decision = view.decision
    assert all(0.0 <= m.p_purchase <= 1.0 for m in decision.margins), decision.margins
    assert decision.best.margin_per_100_eur == max(m.margin_per_100_eur for m in decision.margins)
    assert view.price_now.price_eur == view.state.price_eur
    assert (view.price_best is None) == (decision.action == "keep")


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
    from src.price_curve import get_price_curve
    from src.price_what_if import get_price_what_if

    curve = get_price_curve(client, "SKU-PT-0133")
    centre = next(p for p in curve.curve if p.adjustment_pct == 0)

    what_if = get_price_what_if(client, "SKU-PT-0133", centre.price_eur)

    assert what_if.units >= 0
    assert "price_eur" in {f.field for f in what_if.factors}, what_if.factors
    assert what_if.units == centre.units_sold, (what_if.units, centre.units_sold)


def test_the_forecast_popover_splits_the_knn_estimate_into_rows_that_chain_to_it(client):
    """Inventory and Demand's `?`: the k-NN neighbours share their field terms,
    so the estimate splits into a base, one row per field and the similar
    months (`explain_estimate` raises on a neighbour that doesn't add up)."""
    from src.demand_forecast import forecast_units, forecast_where

    sales = client.search("monthly_sales", where={"product_sku": "SKU-PT-0206"}, limit=200)["hits"]
    _, why = forecast_units(client, "SKU-PT-0206", sales)

    assert why["form"] in ("add", "multiply"), why
    effects = [c["effect"] for c in why["components"]]
    chained = why["base"] * math.prod(effects) if why["form"] == "multiply" else why["base"] + sum(effects)
    assert chained == pytest.approx(why["estimate"])
    fields = [c for c in why["components"] if c["type"] == "field"]
    assert len(fields) == len(forecast_where("SKU-PT-0206", sales[0], 0)), fields


# ── The sandbox's re-scored Shop and the units model (ADR 0043) ─────


def test_schema_meta_reports_the_engine_the_sandbox_template_check_reads(client):
    """`./do sandbox-template-load` refuses a template whose tables aren't on
    engine v2; it reads `"engine"` from `GET /schema/<table>?meta=true`."""
    from src.sandbox_cli import ENGINE_CHECKED

    for table in ENGINE_CHECKED:
        assert client._request("GET", f"/schema/{table}?meta=true").get("engine") == "v2", table


def test_state_band_lifts_are_read_from_why_and_order_as_the_data_does(client):
    """Each discount and star band's shop-wide lift is one factor in `$why`
    (`band_lift` raises otherwise). An offer lifts a purchase over no offer
    by more than ×1.5, and more stars lift it more than fewer."""
    from src.shop_state_lifts import read_state_lifts

    lifts = read_state_lifts(client)

    assert all(lift > 0 for lift in [*lifts.discount.values(), *lifts.rating.values()])
    assert lifts.offer_factor("20+") > 1.5, lifts.discount
    assert lifts.rating["1-2"] < lifts.rating["3"] < lifts.rating["4"] < lifts.rating["5"], lifts.rating


def test_estimate_doesnt_take_a_linked_field_so_the_units_follow_the_price_only(client):
    """Probed 2026-10-24 on 2.11.8: `_estimate units_sold` with
    `product_state.discount_band` in `where` is a 400 "no such field", on
    both models. The Product view's units what-if is by price only, and says
    so. If this starts to pass, the discount can enter the units model."""
    from src.aito_client import AitoError

    where = {"product_sku": "SKU-PT-0143", "product_state.discount_band": "20+"}
    with pytest.raises(AitoError, match="no such field"):
        client.estimate("monthly_sales", where=where, estimate_field="units_sold", model="regression")


def test_paivis_shop_answers_for_the_sandboxes_month_and_holds_her_next_kit_item(client):
    """2026-05 is a month with no contexts yet: `_recommend` still ranks her
    guinea-pig products, and the hideout her kit needs next is among the 40
    the sandbox re-scores (the lever target in docs/demo-script.md)."""
    from src.shop_grid import get_shop_grid
    from src.shop_rescore import RESCORED
    from src.shop_ranking import ranked_items, shop_scope
    from src.shop_context import pets_filter

    scope = shop_scope(client, "paivi", "2026-05", [])
    items = ranked_items(client, scope, {**scope.where(), **pets_filter(scope.pets)}, RESCORED)

    assert all(0 <= i.p <= 1 and i.pet_type == "small_animal" for i in items)
    assert "SKU-PT-0563" in [i.sku for i in items]
    assert get_shop_grid(client, "paivi", "2026-05", [], rescored=True).items


# ── Discount what-if: `_predict purchased` per discount band (ADR 0032) ──


def test_discount_what_if_gives_each_band_a_rate_and_a_lift_that_chain_to_it(client):
    """Each band's `$p` is in [0, 1] and is its `$why` multiplied out
    (`band_estimate` raises otherwise); a discount lifts the band above
    1 and the estimate above no discount; a band the product was never
    shown at still answers (the what-if)."""
    from src.discount_what_if import BANDS, get_discount_what_if

    # Never shown at 15-20 or 20+ on env `observable`.
    result = get_discount_what_if(client, "SKU-PT-0107")

    assert [b.band for b in result.bands] == list(BANDS)
    assert sum(b.current for b in result.bands) == 1
    for band in result.bands:
        assert 0.0 <= band.p_purchase <= 1.0, band
    for band in result.bands[1:]:
        assert band.band_lift is not None and band.band_lift > 1, band
        assert band.vs_no_discount > 1, band
    assert any(b.shown == 0 for b in result.bands), result.bands


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


@pytest.mark.xfail(strict=True, reason=(
    "ADR 0045, amendment 2: the ranked table holds 359 just-bought showings (the shop's list "
    "rarely shows what was just bought; the rest are buy-again lists), too few to judge. "
    "Direction is as registered (clicks 0.198 against 0.315); the sample floor of 600 is not met."))
def test_shop_an_item_bought_last_order_scores_lower_as_just_bought(client):
    """A8's shop form: re-asked with just_bought: true, a product's purchase
    probability drops below what it was before the shopper bought it."""
    from src.shop_context import shopper_where

    context = shopper_where("cat", [], "2026-04")   # Helena's declared pets
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

    result = get_suggestions(client, "paivi", "2026-04", [])

    assert result.owned == {"small_animal": ["cage", "water_bottle"]}, result.owned
    assert result.next_for_pet and "Hideout" in result.next_for_pet[0].name, result.next_for_pet
    assert result.usual, "no usual basket for a shopper with orders"
def test_r5_the_kit_view_shows_an_owner_of_cage_and_bottle_an_add_on_not_another_cage(client):
    """R5, as amended (ADR 0033, 2026-10-21: one view per intent): the kit
    lives in "Next for their kit". For Päivi owning a cage and a bottle in
    April 2026, its first item is an add-on she lacks, never another cage or
    bottle. (The February case, a cage alone in the cart, isn't in the data:
    141 of 145 baskets with a cage also hold the bottle.)"""
    from src.shop_suggestions import get_suggestions

    nxt = get_suggestions(client, "paivi", "2026-04", []).next_for_pet

    assert nxt, "no next item for a kit owner"
    assert any(k in nxt[0].name for k in ("Hideout", "Exercise Wheel", "Tunnel")), [n.name for n in nxt]
    assert not any(n.name.endswith(("Cage", "Water Bottle")) for n in nxt), [n.name for n in nxt]


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


@pytest.mark.xfail(strict=True, reason=(
    "ADR 0045, amendment 2: the ranked table holds 359 just-bought showings (the shop's list "
    "rarely shows what was just bought; the rest are buy-again lists), too few to judge. "
    "Direction is as registered (clicks 0.198 against 0.315); the sample floor of 600 is not met."))
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


def test_patterns_basket_rule_has_a_direction_read_from_its_counts(client, shop_analytics):
    """Basket Rules' confidence and support (ADR 0022), now columns on
    Patterns › Baskets: `fs.f` is the orders holding the other category,
    so the rule reads both ways. Dental treats almost never sell without
    dry food; dry food often sells without dental treats."""
    pairs = {(p.first, p.second): p for p in shop_analytics["baskets"].pairs}
    pair = pairs[("Dog dry-food", "Dog dental-treats")]
    dental = client.search("orders", where={"line_categories": {"$match": "dog_dentaltreats"}}, limit=0)["total"]

    assert pair.orders_with_second == dental
    assert pair.orders == client.search("orders", limit=0)["total"]
    assert 0 < pair.support < pair.confidence < pair.reverse_confidence <= 1, pair


def test_overview_totals_cover_every_order_and_name_the_strongest_pair(client):
    """Overview pages every order and line with `_search` (it raises if the
    pages don't add up), and leads Patterns with the strongest pair."""
    from src.overview_service import get_overview

    overview = get_overview(client)

    kpis = overview["kpis"]
    assert sum(m["orders"] for m in overview["monthly"]) == client.search("orders", limit=0)["total"]
    assert kpis["orders"] > 0 and kpis["months_before"] == 12, kpis
    assert overview["top_products"][0]["units"] >= overview["top_products"][-1]["units"] > 0
    assert sum(h["customers"] for h in overview["households"]) <= kpis["customers"]
    assert (overview["top_basket_pair"]["first"], overview["top_basket_pair"]["second"]) == (
        "Dog dry-food", "Dog dental-treats")


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


# ── Business reorders on UCI Online Retail II, env `uci` (ADR 0034) ──
# Run with `./do uci-check`. Skipped unless AITO_ENV=uci: the pet shop's
# checks above don't hold on this env, and these don't hold on the pet's.


@pytest.fixture(scope="module")
def uci_client() -> AitoClient:
    if os.environ.get("AITO_ENV") != "uci":
        pytest.skip("UCI checks run on env uci only: AITO_ENV=uci (./do uci-check)")
    cfg = load_config()
    c = AitoClient(cfg)
    if not c.check_connectivity():
        pytest.skip(f"Aito not reachable at {cfg.api_base}")
    return c


UCI_REPRODUCTION_CHECKLIST = (
    "If off, check in this order: invoices.month missing or not 'YYYY-MM'; the lines count "
    "(603,034); lines.code linked to products; the cutoff not exactly 2011-09-01; StockCodes "
    "filtered (POST, M and the rest must stay)."
)


def test_uci_draft_reproduces_the_benchmarks_hit_at_1_for_buyers_with_1_2_orders(uci_client):
    """The page's claim: for the 636 buyers with 1-2 orders before the cutoff
    and a next order after it, Aito's top suggestion was in that next order
    for 31 % (197 of 636 in the benchmark, aito-core 625867faca)."""
    from src.uci_outcomes import load_outcomes
    from src.uci_reorder_service import predicted_codes

    buyers = [o for o in load_outcomes().values() if 1 <= o.prior_invoices <= 2 and o.next_order]
    assert len(buyers) == 636, len(buyers)

    hits = 0
    for buyer in buyers:
        codes = predicted_codes(uci_client, buyer.customer_id)
        assert all(0.0 <= p <= 1.0 for _, p in codes), codes
        hits += codes[0][0] in buyer.next_order.codes

    hit_at_1 = hits / len(buyers)
    # The query is deterministic, so the reproduction is exact: the same hits,
    # not a number within a tolerance (±0.01 would be far tighter than the
    # ±0.036 95 % interval at n = 636 anyway).
    assert hits == 197, (
        f"hit@1 {hit_at_1:.4f} ({hits} of {len(buyers)}), benchmark 197 of 636. {UCI_REPRODUCTION_CHECKLIST}")


def test_uci_bought_together_answers_lifts_for_a_common_code(uci_client):
    """85123A (white hanging heart T-light holder) is the most ordered code.
    Its relate must name other codes with lifts and counts that agree with
    a plain count of the baskets holding it."""
    from src.uci_bought_together import MIN_SHARED_INVOICES, bought_together

    result = bought_together(uci_client, "85123A")

    assert result.bought_with, "no code bought with 85123A"
    assert all(b.lift > 0 and b.shared_invoices >= MIN_SHARED_INVOICES for b in result.bought_with)
    assert "85123A" not in {b.code for b in result.bought_with}
    holding = uci_client.search("baskets", where={"codes": {"$match": "85123A"}}, limit=0)["total"]
    assert result.invoices_with_product == holding, (result.invoices_with_product, holding)


def test_uci_backtest_why_names_the_buyer_and_agrees_with_the_measured_ranking(uci_client):
    """ADR 0036's example buyers: the `$why` query (`select` with `{"$why": {}}`,
    limit 1) must rank the same top code as the measured query, and its
    tree must parse to a baseP and lifts with their conditions."""
    from src.backtest_aito import explain_top_suggestion
    from src.uci_outcomes import load_outcomes
    from src.uci_reorder_service import predicted_codes

    buyer = min(c for c, o in load_outcomes().items() if 1 <= o.prior_invoices <= 2 and o.next_order)
    top_code = predicted_codes(uci_client, buyer)[0][0]

    why = explain_top_suggestion(uci_client, buyer, top_code)   # raises if the two rankings disagree

    assert why.startswith("base ") and " when " in why, why


# ── Evidence › Personalised search: the held-out shapes (ADR 0037 §3) ─


def _search_session(session_id: str):
    """A session as the benchmark scores it, from the committed contexts (no impressions needed)."""
    import json
    from pathlib import Path

    from src.personalised_search.sessions import Session

    data = Path(__file__).resolve().parent.parent / "data"
    context = next(c for c in json.loads((data / "contexts.json").read_text()) if c["context_id"] == session_id)
    customer = next(c for c in json.loads((data / "customers.json").read_text())
                    if c["customer_id"] == context["customer"])
    return Session(session_id=session_id, customer=context["customer"], month=context["month"],
                   query=context["search_query"], pets=customer.get("pets"),
                   pets_from_orders=context.get("pets_from_orders"), rule=customer.get("diet"), cart=(),
                   last_order=tuple((context.get("prev_basket") or "").split()), prior_orders=0,
                   bought=frozenset())


def test_a_nested_from_leaves_the_scored_session_out(client):
    """`{"from": "impressions", "where": {"$not": {"context": s}}}` holds none of s's rows,
    so a held-out ranking never reads the purchase it is scored on."""
    from src.personalised_search.rankings import held_out

    assert _count(client, {"context": "SESS-000037"}) > 0
    res = client.search(held_out("SESS-000037"), where={"context": "SESS-000037"}, limit=0)
    assert res["total"] == 0


def test_the_shops_search_held_out_scores_every_allowed_match_and_keeps_the_rule(client):
    """Step 2 of the Shop's search over a nested `from`: a $p in [0, 1] for each
    name match the household's rule allows, and none for rule-breaking food."""
    from src.personalised_search.rankings import shop_search_p, text_lift

    session = _search_session("SESS-000136")          # "cat food", a `sensitive` household
    p = shop_search_p(client, session, list(text_lift(client, session.query)))
    rows = client.search("products", where={"sku": {"$or": list(p)}},
                         select=["sku", "name", "category", "pet_type"], limit=len(p))["hits"]
    assert p and all(0 <= v <= 1 for v in p.values())
    rule_food = [r for r in rows if r["category"] in ("dry-food", "wet-food") and r["pet_type"] in ("dog", "cat")]
    assert rule_food and all("Sensitive" in r["name"] for r in rule_food)


def test_the_history_form_held_out_returns_distinct_products(client):
    """Smart Search's one-query blend, `get product_sku` over a nested `from`."""
    from src.personalised_search.rankings import history_form_ranking

    ranked = history_form_ranking(client, _search_session("SESS-000037"), 20)
    assert len(ranked) == 20 and len(set(ranked)) == 20


def test_the_just_bought_reask_runs_in_a_batch_over_a_nested_from(client):
    from src.personalised_search.rankings import held_out, shop_context
    from src.shop_ranking import _p_true

    session = _search_session("SESS-000136")
    sku = session.last_order[0]
    [answer] = client.batch([{"from": held_out(session.session_id), "predict": "purchased",
                              "where": {**shop_context(session), "product_sku": sku, "just_bought": True}}])
    assert 0 <= _p_true(answer, sku) <= 1


def test_similarity_over_the_name_is_a_standard_bm25(client):
    """ADR 0037's probe, kept: `ln($score)` at θ = 1 follows the Python Okapi BM25,
    so the page may call the left column BM25."""
    import math
    import statistics

    from src.personalised_search.bm25 import Bm25
    from src.personalised_search.sessions import load_products

    products = load_products()
    reference = Bm25({sku: p["name"] for sku, p in products.items()})
    res = client.search("products", order_by={"$similarity": {"name": "senior chicken dog"}, "theta": 1.0},
                        select=["sku", "$score"], limit=1000)
    aito = [h["sku"] for h in res["hits"] if h["$score"] > 1.0]
    assert aito[:10] == reference.ranked("senior chicken dog")[:10]
    ratio = [math.log(h["$score"]) / reference.score("senior chicken dog", h["sku"]) for h in res["hits"][:20]]
    assert 0.95 < statistics.median(ratio) < 1.05, ratio


# ── Reviews (ADR 0039): stars, NPS and churn on data release 2 ───────


def test_reviews_low_stars_cut_clicks_and_purchases_and_high_stars_lift_them(client):
    """R1 and R2: a product shown at 1-2 stars is clicked and bought less than
    the average showing, at 5 stars more, each interval clear of 1."""
    from src.reviews_service import get_reviews_section

    for kpi in ("clicked", "purchased"):
        section = get_reviews_section(client, kpi)
        low = _row(section.rows, "product_state.rating_band", "1-2")
        high = _row(section.rows, "product_state.rating_band", "5")
        assert low and low.interval_high < 1, (kpi, low)
        assert high and high.interval_low > 1, (kpi, high)


def test_reviews_a_negative_review_writer_is_over_represented_among_nps_detractors(client):
    """R3, as the shop sees it: the experience is hidden, but a 1-2 star review
    marks one, and detractors include more of those writers."""
    from src.reviews_service import get_reviews_section

    row = _row(get_reviews_section(client, "nps").rows, "wrote_negative_review", "true")
    assert row and row.interval_low > 1, row


def test_reviews_the_reply_comparison_counts_every_negative_review_month(client):
    """R4b (ADR 0039's amendment): replied and not replied cover every
    customer-month with a negative review, and the ratio sits inside its interval."""
    from src.reviews_service import get_reply_effect, get_reviews_section

    churn = get_reviews_section(client, "churn")
    effect = get_reply_effect(client, churn.clustering)
    negative = client.search("customer_months", where={"had_negative_review": True}, limit=0)["total"]

    assert effect.replied_months + effect.unreplied_months == negative
    assert effect.interval_low < effect.risk_ratio < effect.interval_high


# ── Acquisition (ADR 0040): sources convert and stay differently ─────


def test_acquisition_sources_convert_and_stay_as_planted(client):
    """F2 and F4: email converts best and social worst, each interval apart; the
    affiliate and social customers become regular far less than organic search's."""
    from src.acquisition_service import get_acquisition

    rows = {r.source: r for r in get_acquisition(client).sources}

    assert rows["email"].conversion.low > rows["organic_search"].conversion.high
    assert rows["social"].conversion.high < rows["organic_search"].conversion.low
    for source in ("affiliate", "social"):
        assert rows[source].regular.high < rows["organic_search"].regular.low, source
        assert rows[source].source_lift < 1 < rows["organic_search"].source_lift
