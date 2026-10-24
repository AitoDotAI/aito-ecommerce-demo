"""What markdown clears an overstocked SKU? Supply's action on an overstock row.

For each discount level, Aito estimates next month's units at that price
(`_estimate units_sold`, the regression model the Product view's price
what-if uses, ADR 0029). From the units follow the weeks the excess
takes to sell, and what it frees and costs over the clearance horizon.

The proposal is the shallowest discount that clears the excess within
the horizon:

  - "hold"       full price already clears it: a markdown would only give
                 margin away;
  - "markdown"   the shallowest level that clears it;
  - "wont_clear" no level up to the deepest clears it. A markdown is the
                 wrong tool; the row says so instead of proposing the
                 deepest cut.

The old Markdown view picked the level with the most margin left, so it
proposed cuts that cleared nothing and lost margin on every row (demo
review, 2026-09-28).
"""

from __future__ import annotations

from dataclasses import dataclass

from src.aito_client import AitoClient
from src.demand_forecast import last_month_units, units_at_price

DISCOUNT_LEVELS_PCT = [0, 5, 10, 15, 20]
HORIZON_WEEKS = 13          # a quarter: how long a buyer will wait for stock to clear
WEEKS_PER_MONTH = 4.33


@dataclass(frozen=True)
class MarkdownPoint:
    discount_pct: int
    price_eur: float
    monthly_units: float        # Aito's estimate at this price
    weeks_to_clear: float | None  # None: the estimate is 0 units, it never clears


@dataclass(frozen=True)
class MarkdownProposal:
    action: str                 # "hold" | "markdown" | "wont_clear"
    discount_pct: int           # the proposed level; the deepest for "wont_clear"
    price_eur: float
    weeks_to_clear: float | None
    units_cleared: int          # excess units sold within the horizon at this price
    extra_units_vs_full_price: int
    capital_freed_eur: float    # units_cleared × unit cost
    margin_given_up_eur: float  # (list − proposed price) × units_cleared
    curve: list[MarkdownPoint]


def excess_units(current_stock: int, reorder_point: int) -> int:
    """Stock above twice the reorder point: what a normal cycle doesn't need."""
    return max(0, current_stock - 2 * reorder_point)


def units_within_horizon(monthly_units: float, excess: int) -> int:
    return min(excess, int(monthly_units / WEEKS_PER_MONTH * HORIZON_WEEKS))


def choose(curve: list[MarkdownPoint], excess: int, list_price: float, unit_cost: float) -> MarkdownProposal:
    """The shallowest level that clears `excess` within the horizon (see module doc)."""
    clears = [p for p in curve if p.weeks_to_clear is not None and p.weeks_to_clear <= HORIZON_WEEKS]
    if clears:
        chosen = min(clears, key=lambda p: p.discount_pct)
        action = "hold" if chosen.discount_pct == 0 else "markdown"
    else:
        chosen = max(curve, key=lambda p: p.discount_pct)
        action = "wont_clear"
    full_price = min(curve, key=lambda p: p.discount_pct)
    assert full_price.discount_pct == 0, "the markdown curve must start at full price"
    cleared = units_within_horizon(chosen.monthly_units, excess)
    return MarkdownProposal(
        action=action,
        discount_pct=chosen.discount_pct,
        price_eur=chosen.price_eur,
        weeks_to_clear=chosen.weeks_to_clear,
        units_cleared=cleared,
        extra_units_vs_full_price=cleared - units_within_horizon(full_price.monthly_units, excess),
        capital_freed_eur=round(cleared * unit_cost, 2),
        margin_given_up_eur=round((list_price - chosen.price_eur) * cleared, 2),
        curve=curve,
    )


def propose_markdown(client: AitoClient, sku: str, excess: int, list_price: float,
                     unit_cost: float, profile: dict, sales_rows: list[dict]) -> MarkdownProposal:
    """Estimate units at each level and choose. `profile` carries pet type,
    category and brand: the latest sales row, or the products row."""
    assert excess > 0, f"{sku} has no excess stock to mark down"
    units_last_month = last_month_units(sales_rows)

    def point(pct: int) -> MarkdownPoint:
        price = round(list_price * (1 - pct / 100), 2)
        units = units_at_price(client, sku, profile, units_last_month, price, model="regression")
        weeks = round(excess / (units / WEEKS_PER_MONTH), 1) if units > 0 else None
        return MarkdownPoint(pct, price, round(units, 2), weeks)

    curve = [point(pct) for pct in DISCOUNT_LEVELS_PCT]
    return choose(curve, excess, list_price, unit_cost)
