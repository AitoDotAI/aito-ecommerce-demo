"""Supply — what do I reorder, what is overstocked, and what markdown clears it?

One view for the buyer (ADR 0041), merged from Inventory, Demand,
Markdown and Price's fair-band table. It leads with two decisions:

  1. Reorder: the SKUs below their reorder point, each with Aito's
     next-month forecast (`_estimate units_sold`, `demand_forecast.py`),
     the quantity that covers it plus safety stock, and the revenue the
     stock can't cover.
  2. Overstock: the SKUs far above their reorder point, the capital tied
     in their excess, and for the largest, the markdown that clears it
     (`markdown_proposal.py`).

Below them: the top movers' forecasts, and the SKUs whose list price sits
outside the prices they actually sold at (`price_bands.py`). Each row
carries its price band, so a buyer sees an odd price where they act.

Every forecast is sent once, however many lists show the SKU. Stock
bands, quantities and euros are arithmetic on Aito's estimates and are
labelled as estimates in the view.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass

from src.aito_client import AitoClient
from src.catalogue_reads import products_by_sku, read_all, rows_by_sku
from src.demand_forecast import FORECAST_MONTH, forecast_units, forecast_where, last_month_units
from src.markdown_proposal import excess_units, propose_markdown
from src.price_bands import price_band
from src.supply_rows import (
    MoverRow, OverstockRow, PriceOutlier, ReorderRow, overstock_decision, reorder_decision, stock_band,
)

TOP_MOVERS = 10
MARKDOWN_SCORED = 15     # the largest overstock rows get a markdown sweep (5 estimates each)


@dataclass
class SupplyResponse:
    forecast_month: str
    band_counts: dict
    reorder: dict                   # the decision line: SKUs, units, € at risk
    overstock_decision: dict        # tied capital, and what markdowns would clear
    reorder_queue: list[ReorderRow]
    overstock: list[OverstockRow]
    top_movers: list[MoverRow]
    price_outliers: list[PriceOutlier]
    last_query: dict
    last_response_ms: int

    def to_dict(self) -> dict:
        return asdict(self)


def get_supply(client: AitoClient) -> SupplyResponse:
    started = time.perf_counter()
    stock = read_all(client, "inventory", page=1000)
    products = products_by_sku(client)
    sales = rows_by_sku(read_all(client, "monthly_sales"))
    bands = {sku: price_band([float(s["price_eur"]) for s in rows], float(products[sku]["price_eur"]))
             for sku, rows in rows_by_sku(read_all(client, "product_states")).items()}

    by_band: dict[str, list[dict]] = {"critical": [], "low": [], "ok": [], "overstock": []}
    for row in stock:
        by_band[stock_band(int(row["current_stock"]), int(row["reorder_point"]))].append(row)
    movers = sorted(sales, key=lambda sku: -_average_units(sales[sku]))[:TOP_MOVERS]

    # One forecast per SKU, shared by the reorder queue and the top movers.
    to_forecast = sorted({r["sku"] for r in by_band["critical"] if r["sku"] in sales} | set(movers))
    with ThreadPoolExecutor(max_workers=8) as pool:
        forecasts = dict(zip(to_forecast, pool.map(lambda sku: forecast_units(client, sku, sales[sku]),
                                                   to_forecast)))

    reorder_queue = sorted(
        (ReorderRow.build(r, products[r["sku"]], forecasts.get(r["sku"]), bands.get(r["sku"]))
         for r in by_band["critical"]),
        key=lambda row: -row.revenue_at_risk_eur)

    overstock = sorted(by_band["overstock"], key=lambda r: -_tied_capital(r))
    with ThreadPoolExecutor(max_workers=4) as pool:
        proposals = list(pool.map(lambda r: _markdown(client, r, products[r["sku"]], sales.get(r["sku"], [])),
                                  overstock[:MARKDOWN_SCORED]))
    overstock_rows = [OverstockRow.build(r, products[r["sku"]], bands.get(r["sku"]), proposal)
                      for r, proposal in zip(overstock[:MARKDOWN_SCORED], proposals)]

    top_movers = [MoverRow.build(sku, products[sku], sales[sku], forecasts[sku],
                                 next(r for r in stock if r["sku"] == sku))
                  for sku in movers]
    outliers = sorted((PriceOutlier.build(sku, products[sku], band) for sku, band in bands.items() if band.outlier),
                      key=lambda o: -o.above_band_pct)

    return SupplyResponse(
        forecast_month=FORECAST_MONTH,
        band_counts={band: len(rows) for band, rows in by_band.items()},
        reorder=reorder_decision(reorder_queue),
        overstock_decision=overstock_decision(
            skus=len(overstock), tied_capital_eur=sum(_tied_capital(r) for r in overstock), rows=overstock_rows),
        reorder_queue=reorder_queue,
        overstock=overstock_rows,
        top_movers=top_movers,
        price_outliers=outliers,
        last_query=_forecast_query(to_forecast[0], sales) if to_forecast else
        {"endpoint": "_estimate", "body": {"note": "No SKU needed a forecast, so no _estimate was sent."}},
        last_response_ms=int((time.perf_counter() - started) * 1000),
    )


def _average_units(rows: list[dict]) -> float:
    return sum(int(r["units_sold"]) for r in rows) / len(rows)


def _tied_capital(row: dict) -> float:
    return excess_units(int(row["current_stock"]), int(row["reorder_point"])) * float(row["unit_cost_eur"])


def _markdown(client: AitoClient, row: dict, product: dict, sales_rows: list[dict]):
    # A SKU that never sold is profiled from the catalogue (pet type, category, brand).
    profile = max(sales_rows, key=lambda r: r["month"]) if sales_rows else product
    return propose_markdown(
        client, row["sku"], excess_units(int(row["current_stock"]), int(row["reorder_point"])),
        float(product["price_eur"]), float(row["unit_cost_eur"]), profile, sales_rows)


def _forecast_query(sku: str, sales: dict[str, list[dict]]) -> dict:
    """The forecast body exactly as sent for `sku`, for the Aito panel."""
    rows = sales[sku]
    return {"endpoint": "_estimate", "body": {
        "from": "monthly_sales",
        "where": forecast_where(sku, max(rows, key=lambda r: r["month"]), last_month_units(rows)),
        "estimate": "units_sold",
        "select": ["estimate", "why"],
    }}
