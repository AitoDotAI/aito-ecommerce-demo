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
SUPPLY_SNAPSHOT = "inventory"
RETENTION_SNAPSHOT = "churn"


@dataclass(frozen=True)
class Headline:
    view: str          # "Patterns"
    href: str          # "/patterns/?anchor=dog_dryfood"
    headline: str      # the decision, with its number
    detail: str        # the reason, or what else the view holds
    available: bool = True


def _kpi(snapshot: dict, label: str) -> float:
    values = [k["value"] for k in snapshot["kpis"] if k["label"] == label]
    if len(values) != 1:
        raise KeyError(f"the snapshot has {len(values)} KPIs labelled {label!r}")
    return values[0]


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


def supply_headline(inventory: dict | None) -> Headline:
    href = "/supply/"
    if inventory is None:
        return _missing("Supply", href, SUPPLY_SNAPSHOT)
    critical, at_risk = int(_kpi(inventory, "Critical")), _kpi(inventory, "Revenue at risk")
    overstock, tied = int(_kpi(inventory, "Overstock")), _kpi(inventory, "Tied capital")
    return Headline(
        "Supply", href,
        f"Reorder {critical} products below their reorder point: about €{at_risk:,.0f} of next month's "
        f"sales is at risk if they run out (estimated from Aito's forecast).",
        f"{overstock} more hold €{tied:,.0f} of stock above need: candidates for a markdown.",
    )


def retention_headline(churn: dict | None) -> Headline:
    href = "/retention/"
    if churn is None:
        return _missing("Retention", href, RETENTION_SNAPSHOT)
    churned, total = int(_kpi(churn, "Churned")), int(_kpi(churn, "Total customers"))
    risers = [d for d in churn["drivers"] if d["lift"] > 1]
    detail = "The at-risk list, and the offer that brings each back, are in Retention."
    if risers:
        d = max(risers, key=lambda r: r["lift"])
        detail = (f"Customers with {d['field']} {d['value'].replace('_', ' ')} left at "
                  f"{d['churn_rate']:.0%}, against {d['churn_rate_overall']:.0%} overall. " + detail)
    return Headline(
        "Retention", href,
        f"Win back {churned:,} of {total:,} customers ({churned / total:.0%}) who haven't ordered in 90 days.",
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
