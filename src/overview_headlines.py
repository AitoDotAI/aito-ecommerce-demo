"""Overview's headlines: one per owner view, each a link (ADR 0041).

Every number in a headline comes from data: the Overview's own payload
(`src/overview_service.py`) for Patterns and Product, and the answer the
linked view itself serves for Supply and Retention (its snapshot, or its
live answer once that is cached), so the headline and the view it opens
can't disagree. Nothing here queries Aito: computing Retention live takes
20 s cold, too long for the landing page.

When the view has no answer yet, its card is left out, and the server
logs which one and why. The page never shows a command-line hint: the
Overview is what a visitor sees first.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Callable

logger = logging.getLogger(__name__)

# The precomputed view each headline reads (`src/precompute.py`).
SUPPLY_SNAPSHOT = "supply"
RETENTION_SNAPSHOT = "retention"


@dataclass(frozen=True)
class Headline:
    view: str          # "Patterns"
    href: str          # "/patterns/?anchor=dog_dryfood"
    headline: str      # the decision, with its number
    detail: str        # the reason, or what else the view holds


def _missing(view: str, name: str) -> None:
    logger.warning("Overview leaves out the %s card: no %s snapshot, and the view's live answer "
                   "isn't cached yet (./do precompute makes the snapshot)", view, name)


def patterns_headline(overview: dict) -> Headline:
    p = overview["top_basket_pair"]
    first, second = p["first"], p["second"].lower()
    without = p["orders_with_first"] - p["orders_with_both"]
    return Headline(
        "Patterns", f"/patterns/?anchor={p['first_id']}",
        f"{first} baskets hold {second} {p['lift']:.2f}× as often as the average basket "
        f"[{p['interval_low']:.2f}–{p['interval_high']:.2f}]: put them together in the cart and the drawer.",
        f"{p['orders_with_both']:,} of {p['orders_with_first']:,} {first.lower()} orders "
        f"({p['confidence']:.0%}) already hold {second}; {without:,} don't.",
    )


def product_headline(overview: dict) -> Headline:
    best, k = overview["top_products"][0], overview["kpis"]
    return Headline(
        "Product", f"/product/?sku={best['sku']}",
        f"Best seller: {best['name']}, {best['units']:,} units in {k['first_month']} … {k['last_month']}.",
        "See what it will sell next month, why, and what a discount would do.",
    )


def supply_headline(supply: dict | None) -> Headline | None:
    """Supply's two decision lines (`src/supply_rows.py`), as Supply leads with them."""
    href = "/supply/"
    if supply is None:
        return _missing("Supply", SUPPLY_SNAPSHOT)
    reorder, over = supply["reorder"], supply["overstock_decision"]
    detail = f"{over['skus']} overstocked products hold €{over['tied_capital_eur']:,.0f}"
    if over["wont_clear"]:
        detail += (f"; of the {over['scored']} largest, {over['wont_clear']} don't clear by price alone "
                   f"(an offer's lift on purchases and placement isn't counted)")
    return Headline(
        "Supply", href,
        f"Reorder {reorder['skus']} products now: about €{reorder['revenue_at_risk_eur']:,.0f} of next month's "
        f"sales is at risk without them, if it sells like the last three months.",
        detail + ".",
    )


def retention_headline(retention: dict | None) -> Headline | None:
    """Retention's decision line (`src/retention_service.py`) and its strongest observed driver."""
    href = "/retention/"
    if retention is None:
        return _missing("Retention", RETENTION_SNAPSHOT)
    decision = retention["decision"]
    risers = [d for d in retention["drivers"] if d["lift"] > 1]
    detail = "Each has a win-back offer to send, where past emails can tell one."
    if risers:
        d = max(risers, key=lambda r: r["lift"])
        detail = (f"Customers with {d['field']} {d['value'].replace('_', ' ')} left at "
                  f"{d['churn_rate']:.0%}, against {d['churn_rate_overall']:.0%} overall. " + detail)
    return Headline(
        "Retention", href,
        f"Reach {decision['customers']} customers first: €{decision['spend_12m_eur']:,.0f} of last year's spend, "
        f"each more likely than not to stop ordering, by Aito's estimate.",
        detail,
    )


EVIDENCE = Headline(
    "Evidence", "/evidence/",
    "How well does each prediction work, and against what baseline?",
    "Business reorders on real retail data, personalised search, and the model checks.",
)


def owner_headlines(overview: dict, view_data: Callable[[str], dict | None]) -> list[dict]:
    """`view_data(name)` returns the data a view serves, or None when it has none ready."""
    headlines = (
        patterns_headline(overview),
        product_headline(overview),
        supply_headline(view_data(SUPPLY_SNAPSHOT)),
        retention_headline(view_data(RETENTION_SNAPSHOT)),
        EVIDENCE,
    )
    return [asdict(h) for h in headlines if h is not None]
