"""The decision the Product view leads with (src/product_decision.py).

Pure arithmetic over the discount what-if's estimates: which band's
showings earn the most margin, and the break-even beside it. The numbers
below are env `observable`'s for SKU-PT-0192 (list €2.78, cost €1.39).
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from src.discount_what_if import BandEstimate
from src.product_decision import decide_offer

P = {"none": 0.2657, "10-15": 0.4189, "15-20": 0.4326, "20+": 0.4218}


def bands(p=P, current="none") -> list[BandEstimate]:
    return [BandEstimate(band=b, p_purchase=v, vs_no_discount=v / p["none"], band_lift=None, product_lift=None,
                         base_p=0.12, normaliser=1.0, calibrated=False, shown=0, purchased=0, current=b == current)
            for b, v in p.items()]


def test_a_shallow_offer_wins_when_its_lift_outruns_the_margin_it_gives_up():
    decision = decide_offer(bands(), list_price_eur=2.78, unit_cost_eur=1.39)

    # 100 × 0.2657 × (2.78 − 1.39) = €36.93; at 12.5 % off, 100 × 0.4189 × (2.43 − 1.39) = €43.57.
    assert (decision.action, decision.best_band) == ("offer", "10-15")
    assert decision.current.margin_per_100_eur == pytest.approx(36.93, abs=0.01)
    assert decision.best.margin_per_100_eur == pytest.approx(43.57, abs=0.01)
    # It must sell 1.39 / 1.04 = 1.34× as often to break even; Aito expects 1.58×.
    assert decision.breakeven_ratio == pytest.approx(1.337, abs=0.001)
    assert decision.expected_ratio == pytest.approx(1.577, abs=0.001)


def test_a_thin_margin_keeps_the_list_price():
    # At a cost of €2.30, 12.5 % off leaves €0.13 a sale: no lift pays for that.
    decision = decide_offer(bands(), list_price_eur=2.78, unit_cost_eur=2.30)

    assert (decision.action, decision.best_band) == ("keep", "none")
    assert decision.breakeven_ratio is None


def test_an_offer_that_earns_less_than_list_price_is_advised_to_end():
    decision = decide_offer(bands(current="20+"), list_price_eur=2.78, unit_cost_eur=2.30)

    assert (decision.action, decision.current_band) == ("end_offer", "20+")


def test_moving_from_one_offer_to_a_better_one_is_a_change():
    decision = decide_offer(bands(current="20+"), list_price_eur=2.78, unit_cost_eur=1.39)

    assert (decision.action, decision.best_band) == ("change", "10-15")


def test_each_band_is_priced_at_its_typical_discount():
    margins = decide_offer(bands(), list_price_eur=10.0, unit_cost_eur=5.0).margins

    assert [(m.band, m.price_eur) for m in margins] == [
        ("none", 10.0), ("10-15", 8.75), ("15-20", 8.25), ("20+", 7.75)]


def test_estimates_out_of_band_order_are_refused():
    shuffled = bands()[::-1]
    with pytest.raises(ValueError, match="one estimate per band"):
        decide_offer(shuffled, list_price_eur=2.78, unit_cost_eur=1.39)


def test_exactly_one_band_must_be_current():
    two_current = [replace(b, current=True) for b in bands()]
    with pytest.raises(ValueError):
        decide_offer(two_current, list_price_eur=2.78, unit_cost_eur=1.39)
