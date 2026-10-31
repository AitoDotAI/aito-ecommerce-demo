"""Supply's rows and decision lines: arithmetic on stock and on what each SKU sold lately.

Stock bands are the shop's own rule, from the `inventory` table's reorder
point. Reorder quantities and euros assume next month sells like the last
three (`recent_units`): observed sales, because Aito's per-product forecast
only ties the naive rule (Evidence › Model checks), so it sets no quantity
and no euro figure here. Aito's estimates remain in the markdown sweep.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.demand_forecast import last_month_units, recent_units
from src.markdown_proposal import MarkdownProposal, excess_units
from src.price_bands import PriceBand


def stock_band(current_stock: int, reorder_point: int) -> str:
    if current_stock < reorder_point:
        return "critical"
    if current_stock < reorder_point * 1.5:
        return "low"
    if current_stock > reorder_point * 5:
        return "overstock"
    return "ok"


@dataclass(frozen=True)
class ReorderRow:
    sku: str
    name: str
    category: str
    supplier: str
    lead_time_days: int
    current_stock: int
    reorder_point: int
    recent_units: int              # units a month it sold over the last three months: observed; 0 when it never sold
    order_qty: int                 # recent units + safety stock − stock on hand
    order_cost_eur: float          # order_qty × unit cost
    revenue_at_risk_eur: float     # recent units the stock can't cover × list price
    price: PriceBand | None

    @classmethod
    def build(cls, stock: dict, product: dict, sales_rows: list[dict], price: PriceBand | None) -> "ReorderRow":
        units = recent_units(sales_rows)
        on_hand = int(stock["current_stock"])
        # A SKU that never sold gets an order that only restores safety stock.
        qty = max(0, units + int(stock["safety_stock"]) - on_hand)
        shortfall = max(0, units - on_hand)
        return cls(
            sku=stock["sku"], name=product["name"], category=product["category"],
            supplier=str(stock["supplier"]), lead_time_days=int(stock["lead_time_days"]),
            current_stock=on_hand, reorder_point=int(stock["reorder_point"]),
            recent_units=units, order_qty=qty,
            order_cost_eur=round(qty * float(stock["unit_cost_eur"]), 2),
            revenue_at_risk_eur=round(shortfall * float(product["price_eur"]), 2),
            price=price,
        )


@dataclass(frozen=True)
class OverstockRow:
    sku: str
    name: str
    category: str
    current_stock: int
    reorder_point: int
    excess_units: int              # stock above twice the reorder point
    unit_cost_eur: float
    tied_capital_eur: float        # excess × unit cost
    price: PriceBand | None
    markdown: MarkdownProposal

    @classmethod
    def build(cls, stock: dict, product: dict, price: PriceBand | None,
              markdown: MarkdownProposal) -> "OverstockRow":
        excess = excess_units(int(stock["current_stock"]), int(stock["reorder_point"]))
        cost = float(stock["unit_cost_eur"])
        return cls(
            sku=stock["sku"], name=product["name"], category=product["category"],
            current_stock=int(stock["current_stock"]), reorder_point=int(stock["reorder_point"]),
            excess_units=excess, unit_cost_eur=round(cost, 2), tied_capital_eur=round(excess * cost, 2),
            price=price, markdown=markdown,
        )


@dataclass(frozen=True)
class MoverRow:
    sku: str
    name: str
    category: str
    avg_monthly_units: int
    last_month_units: int
    recent_units: int              # units a month over the last three months
    current_stock: int

    @classmethod
    def build(cls, sku: str, product: dict, sales_rows: list[dict], stock: dict) -> "MoverRow":
        return cls(
            sku=sku, name=product["name"], category=product["category"],
            avg_monthly_units=round(sum(int(r["units_sold"]) for r in sales_rows) / len(sales_rows)),
            last_month_units=last_month_units(sales_rows), recent_units=recent_units(sales_rows),
            current_stock=int(stock["current_stock"]),
        )


@dataclass(frozen=True)
class PriceOutlier:
    sku: str
    name: str
    category: str
    price: PriceBand
    above_band_pct: float          # how far the list price sits above the band; negative below it

    @classmethod
    def build(cls, sku: str, product: dict, price: PriceBand) -> "PriceOutlier":
        if price.list_price_eur > price.band_high_eur:
            off = price.list_price_eur / price.band_high_eur - 1
        else:
            off = price.list_price_eur / price.band_low_eur - 1
        return cls(sku=sku, name=product["name"], category=product["category"], price=price,
                   above_band_pct=round(off * 100, 1))


def reorder_decision(rows: list[ReorderRow]) -> dict:
    to_order = [r for r in rows if r.order_qty > 0]
    return {
        "skus": len(to_order),
        "units": sum(r.order_qty for r in to_order),
        "order_cost_eur": round(sum(r.order_cost_eur for r in to_order), 2),
        "revenue_at_risk_eur": round(sum(r.revenue_at_risk_eur for r in rows), 2),
    }


def overstock_decision(*, skus: int, tied_capital_eur: float, rows: list[OverstockRow]) -> dict:
    """The overstock line: all overstock capital, and what the scored rows' markdowns do."""
    by_action = {a: [r for r in rows if r.markdown.action == a] for a in ("hold", "markdown", "wont_clear")}
    marked = by_action["markdown"]
    return {
        "skus": skus,
        "tied_capital_eur": round(tied_capital_eur, 2),
        "scored": len(rows),
        "hold": len(by_action["hold"]),
        "markdown": len(marked),
        "wont_clear": len(by_action["wont_clear"]),
        "markdown_units_cleared": sum(r.markdown.units_cleared for r in marked),
        "markdown_capital_freed_eur": round(sum(r.markdown.capital_freed_eur for r in marked), 2),
        "markdown_margin_given_up_eur": round(sum(r.markdown.margin_given_up_eur for r in marked), 2),
    }
