"""The decision the Product view leads with: which discount band, if any.

Aito's discount what-if (`src/discount_what_if.py`) gives the chance the
product is bought when it is shown, per band. A deeper discount sells
more often but earns less per sale, so the bands are compared on what a
showing earns:

    margin per 100 showings = 100 × P(bought | shown) × (price − unit cost)

at each band's typical discount (its midpoint; the data's medians are
within 0.2 points of it). This counts one unit per purchase and assumes
the product is shown as often as now. Both are said on the page.

The band with the most margin per showing is the advice. Beside it,
the break-even: how much more often an offer must sell to earn what the
list price earns, against how much more often Aito expects it to sell.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from src.discount_what_if import BANDS, BandEstimate

# A band's typical discount, in per cent off the list price.
BAND_DISCOUNT_PCT = {"none": 0.0, "10-15": 12.5, "15-20": 17.5, "20+": 22.5}
assert set(BAND_DISCOUNT_PCT) == set(BANDS)


@dataclass(frozen=True)
class BandMargin:
    band: str
    price_eur: float              # the list price less the band's typical discount
    p_purchase: float             # Aito's estimate, bought when shown
    margin_per_100_eur: float     # 100 × p × (price − cost)


@dataclass(frozen=True)
class OfferDecision:
    action: str                   # "keep" | "offer" | "change" | "end_offer"
    current_band: str
    best_band: str
    current: BandMargin
    best: BandMargin
    breakeven_ratio: float | None  # sales needed vs list price, for the best band; None when it is "none"
    expected_ratio: float          # Aito's p at the best band / p at no discount
    margins: list[BandMargin]

    def to_dict(self) -> dict:
        return asdict(self)


def decide_offer(bands: list[BandEstimate], list_price_eur: float, unit_cost_eur: float) -> OfferDecision:
    """The band whose showings earn the most, and how it compares with now."""
    if [b.band for b in bands] != list(BANDS):
        raise ValueError(f"expected one estimate per band {BANDS}, got {[b.band for b in bands]}")
    margins = [_margin(b, list_price_eur, unit_cost_eur) for b in bands]
    best = max(margins, key=lambda m: m.margin_per_100_eur)
    [current_estimate] = [b for b in bands if b.current]
    current = next(m for m in margins if m.band == current_estimate.band)
    at_list = margins[0]

    if best.band == current.band:
        action = "keep"
    elif best.band == "none":
        action = "end_offer"
    else:
        action = "offer" if current.band == "none" else "change"

    margin_at_list = list_price_eur - unit_cost_eur
    margin_at_best = best.price_eur - unit_cost_eur
    breakeven = (margin_at_list / margin_at_best
                 if best.band != "none" and margin_at_best > 0 else None)
    return OfferDecision(
        action=action,
        current_band=current.band,
        best_band=best.band,
        current=current,
        best=best,
        breakeven_ratio=round(breakeven, 3) if breakeven is not None else None,
        expected_ratio=round(best.p_purchase / at_list.p_purchase, 3),
        margins=margins,
    )


def _margin(estimate: BandEstimate, list_price_eur: float, unit_cost_eur: float) -> BandMargin:
    price = round(list_price_eur * (1 - BAND_DISCOUNT_PCT[estimate.band] / 100), 2)
    return BandMargin(
        band=estimate.band,
        price_eur=price,
        p_purchase=estimate.p_purchase,
        margin_per_100_eur=round(100 * estimate.p_purchase * (price - unit_cost_eur), 2),
    )
