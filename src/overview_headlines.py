"""Overview's headlines: one per owner view, each a link (ADR 0041).

Every number in a headline comes from data: the Overview's own payload
(`src/overview_service.py`) for Patterns and Product, and the snapshot
the linked view itself serves for Supply and Retention, so the headline
and the view it opens can't disagree. Nothing here queries Aito.

A missing snapshot shows as an unavailable headline that names the
command to make it, rather than as a quietly absent tile.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable

# The precomputed view each headline reads (`src/precompute.py`).
SUPPLY_SNAPSHOT = "supply"
RETENTION_SNAPSHOT = "retention"


@dataclass(frozen=True)
class Headline:
    view: str          # "Patterns"
    href: str          # "/patterns/?anchor=dog_dryfood"
    headline: str      # the decision, with its number
    detail: str        # the reason, or what else the view holds
    available: bool = True


def _missing(view: str, href: str, name: str) -> Headline:
    return Headline(view, href, f"No {name} snapshot for this data yet",
                    "Run ./do precompute to make one.", available=False)


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


def supply_headline(supply: dict | None) -> Headline:
    """Supply's two decision lines (`src/supply_rows.py`), as Supply leads with them."""
    href = "/supply/"
    if supply is None:
        return _missing("Supply", href, SUPPLY_SNAPSHOT)
    reorder, over = supply["reorder"], supply["overstock_decision"]
    detail = f"{over['skus']} overstocked products hold €{over['tied_capital_eur']:,.0f}"
    if over["wont_clear"]:
        detail += (f"; of the {over['scored']} largest, {over['wont_clear']} won't clear even with a markdown, "
                   f"by Aito's estimate")
    return Headline(
        "Supply", href,
        f"Reorder {reorder['skus']} products now: about €{reorder['revenue_at_risk_eur']:,.0f} of next month's "
        f"sales is at risk without them (estimated from Aito's forecast).",
        detail + ".",
    )


def retention_headline(retention: dict | None) -> Headline:
    """Retention's decision line (`src/retention_service.py`) and its strongest observed driver."""
    href = "/retention/"
    if retention is None:
        return _missing("Retention", href, RETENTION_SNAPSHOT)
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


def owner_headlines(overview: dict, snapshot: Callable[[str], dict | None]) -> list[dict]:
    """`snapshot(name)` returns a precomputed view's data, or None."""
    return [asdict(h) for h in (
        patterns_headline(overview),
        product_headline(overview),
        supply_headline(snapshot(SUPPLY_SNAPSHOT)),
        retention_headline(snapshot(RETENTION_SNAPSHOT)),
        EVIDENCE,
    )]
