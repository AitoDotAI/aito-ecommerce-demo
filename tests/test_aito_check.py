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
