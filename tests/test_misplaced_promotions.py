"""M1, misplaced promotions (docs/verification/misplaced-promotions-prereg.md).

Some promotions give the discount away and move nothing: for those SKUs a
shopper's odds, the ranker's placement and the offer landing page see the
product at full price, while the price paid stays discounted.
"""

import dataclasses
import random
from collections import Counter

import data.generate_fixtures as generator
from data import catalogue_events, lifecycle, planted_switches, sensitivities


def _promotions(seed: int = 42) -> lifecycle.Promotions:
    products = generator.gen_products(random.Random(seed))
    return lifecycle.plan_promotions(random.Random(seed + 27), products, generator._MONTH_WINDOW)


def _state(sku: str, discount_pct: float) -> catalogue_events.ProductState:
    on = discount_pct >= catalogue_events.OFFER_MIN_PCT
    return catalogue_events.ProductState(
        product_state_id=f"{sku}-2026-03", product_sku=sku, month="2026-03", price_eur=10.0 * (1 - discount_pct / 100),
        list_price_eur=10.0, discount_pct=discount_pct, on_offer=on, discount_band="20+" if on else "none",
        rating_band="4", age="established", rival_launched=False, price_change="none", list_price_index=1.0,
        list_price_band="100", label="none", stock="in_stock", review_count_band="5-19", image_count="2-3",
        description_quality="ok", ad_level="none")


def test_the_switch_is_on():
    assert planted_switches.ON["M1"] is True


def test_misplaced_skus_are_drawn_from_promoted_ones_outside_the_mispriced():
    promotions = _promotions()
    misplaced = lifecycle.plan_misplaced(42, promotions)
    months_on_offer = Counter(sku for sku, _ in promotions.discount)
    assert len(misplaced) == lifecycle.N_MISPLACED == 15
    assert all(months_on_offer[sku] >= lifecycle.MISPLACED_MIN_MONTHS == 3 for sku in misplaced)
    assert not misplaced & promotions.mispriced
    # its own RNG: the same draw every time, and a different seed draws differently
    assert lifecycle.plan_misplaced(42, promotions) == misplaced
    assert lifecycle.plan_misplaced(7, promotions) != misplaced
    # planning them leaves the promotions as they were
    assert promotions.misplaced == frozenset()


def test_a_misplaced_offer_is_felt_as_full_price_and_still_discounted():
    promotions = dataclasses.replace(_promotions(), misplaced=frozenset({"SKU-X"}))
    offer, full = _state("SKU-X", 20.0), _state("SKU-X", 0.0)
    felt = generator._felt(promotions, offer)
    # what a shopper and the ranker see: no offer
    assert (felt.on_offer, felt.discount_pct, felt.discount_band) == (False, 0.0, "none")
    assert sensitivities.state_odds(felt, {"discount": "high", "stars": "mid", "newness": "mid", "labels": "mid"}) == \
        sensitivities.state_odds(full, {"discount": "high", "stars": "mid", "newness": "mid", "labels": "mid"})
    # what is recorded and paid: the discount
    assert (offer.on_offer, offer.price_eur) == (True, 8.0)
    # another SKU's offer works as before
    working = _state("SKU-Y", 20.0)
    assert generator._felt(promotions, working) is working


def test_switched_off_nothing_is_misplaced(monkeypatch):
    monkeypatch.setitem(planted_switches.ON, "M1", False)
    assert generator._misplaced(42, _promotions()) == frozenset()
