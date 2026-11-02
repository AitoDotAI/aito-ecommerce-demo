"""The metrics of ADR 0038's planted effects: a product's state, by the shopper's sensitivity.

Each returns one number from one generated data dir; `scripts/planted_effects.py`
compares it between a planted generation and its null
(docs/verification/actionable-states-prereg.md). The `high` ÷ `low` checks
call a metric once per sensitivity level.
"""
from __future__ import annotations

from scripts.planted_effect_metrics import Fixtures, _rate

RANDOM_LABELS = ("recommended", "staff_pick")


def _contrast(rows, in_a, in_b, outcome: str = "purchased") -> float:
    """The outcome's rate among rows `in_a` ÷ among rows `in_b`."""
    rows = list(rows)
    return _rate((r for r in rows if in_a(r)), outcome) / _rate((r for r in rows if in_b(r)), outcome)


def _of(fx: Fixtures, sensitivity: str, level: str) -> list[dict]:
    return [r for r in fx.impressions() if r[f"{sensitivity}_sensitivity"] == level]


def offer_contrast(fx: Fixtures, level: str) -> float:
    """P6: purchase rate on offer ÷ not, among shoppers at this discount sensitivity."""
    state = fx.state()
    return _contrast(_of(fx, "discount", level),
                     lambda r: state[r["product_state"]]["on_offer"],
                     lambda r: not state[r["product_state"]]["on_offer"])


def stars_contrast(fx: Fixtures, level: str) -> float:
    """P7: purchase rate at 5 stars ÷ at 1–2, among shoppers at this stars sensitivity."""
    state = fx.state()
    return _contrast(_of(fx, "stars", level),
                     lambda r: state[r["product_state"]]["rating_band"] == "5",
                     lambda r: state[r["product_state"]]["rating_band"] == "1-2")


def newness_contrast(fx: Fixtures, level: str) -> float:
    """P8: on launched products, purchase rate while new ÷ once established."""
    state, launches = fx.state(), fx.launches()
    rows = [r for r in _of(fx, "newness", level) if r["product_sku"] in launches]
    return _contrast(rows, lambda r: state[r["product_state"]]["age"] == "new",
                     lambda r: state[r["product_state"]]["age"] == "established")


def random_label_contrast(fx: Fixtures, level: str) -> float:
    """P9: purchase rate with a label the shop drew at random ÷ unlabelled."""
    state = fx.state()
    return _contrast(_of(fx, "labels", level),
                     lambda r: state[r["product_state"]]["label"] in RANDOM_LABELS,
                     lambda r: state[r["product_state"]]["label"] == "none")


def popular_label_contrast(fx: Fixtures, level: str) -> float:
    """P9p: the same for `popular`, a rule (so confounded with what sells)."""
    state = fx.state()
    return _contrast(_of(fx, "labels", level),
                     lambda r: state[r["product_state"]]["label"] == "popular",
                     lambda r: state[r["product_state"]]["label"] == "none")


def low_stock_purchase_given_cart(fx: Fixtures) -> float:
    """P10: P(purchase | added to cart) on impressions of a product low on stock."""
    state = fx.state()
    return _rate(r for r in fx.impressions()
                 if r["added_to_cart"] and state[r["product_state"]]["stock"] == "low")


def offer_share_tracks_discount_sensitivity(fx: Fixtures) -> float:
    """V1: P(discount-high | offer_share high) ÷ P(discount-high | offer_share low), over contexts."""
    traits = fx.traits()
    rows = [{"high": traits[c["customer"]]["discount_sensitivity"] == "high", "band": c["offer_share"]}
            for c in fx.load("contexts") if "customer" in c]
    return _contrast(rows, lambda r: r["band"] == "high", lambda r: r["band"] == "low", "high")
