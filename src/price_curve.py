"""A product's demand curve: next month's units at seven prices (ADR 0016,
ADR 0029), for the Product view's price what-if.

Seven `_estimate units_sold` calls with the regression model, at the
product's average selling price and ±3, 7 and 10 % from it, in parallel.
The evidence is the Demand forecast's (`src/demand_forecast.py`) plus the
price. Beside the curve, the product's own months: what it sold at what
price, and the profit at its unit cost.

Cached 30 min per product.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass

from src import cache
from src.aito_client import AitoClient, AitoError
from src.demand_forecast import last_month_units, price_where, units_at_price
from src.lookup_errors import UnknownProductError

# Constrained to ±10 %: the data's prices span ±18 % at most, and beyond
# that the regression's price slope is extrapolated. A 10 % move is also
# the kind of pricing decision a manager would consider.
CURVE_ADJUSTMENTS_PCT: list[int] = [-10, -7, -3, 0, 3, 7, 10]


@dataclass(frozen=True)
class HistoricalPoint:
    month: str
    price_eur: float
    units_sold: int
    revenue_eur: float
    profit_eur: float


@dataclass(frozen=True)
class CurvePoint:
    price_eur: float
    units_sold: float       # _estimate returns a float
    profit_eur: float
    adjustment_pct: int     # one of CURVE_ADJUSTMENTS_PCT


@dataclass
class PriceCurve:
    sku: str
    name: str
    list_price_eur: float
    unit_cost_eur: float
    mean_price_eur: float
    historical: list[HistoricalPoint]
    curve: list[CurvePoint]
    last_query: dict
    last_response_ms: int

    def to_dict(self) -> dict:
        return asdict(self)


def get_price_curve(client: AitoClient, sku: str) -> PriceCurve:
    cache_key = f"price-curve:{sku}"
    cached = cache.get(cache_key)
    if cached:
        return _from_dict(cached)

    started = time.perf_counter()
    products = client.search("products", where={"sku": sku}, limit=1)["hits"]
    if not products:
        raise UnknownProductError(f"No product {sku} in the catalogue")
    product = products[0]
    inventory = client.search("inventory", where={"sku": sku}, limit=1)["hits"]
    if not inventory:
        raise AitoError(f"{sku} has no inventory row, so it has no unit cost")
    unit_cost = float(inventory[0]["unit_cost_eur"])
    sales = sorted(client.search("monthly_sales", where={"product_sku": sku}, limit=200)["hits"],
                   key=lambda r: r["month"])

    historical = [
        HistoricalPoint(
            month=row["month"],
            price_eur=round(float(row["price_eur"]), 2),
            units_sold=int(row["units_sold"]),
            revenue_eur=round(float(row["revenue_eur"]), 2),
            profit_eur=round((float(row["price_eur"]) - unit_cost) * int(row["units_sold"]), 2),
        )
        for row in sales
    ]
    list_price = float(product["price_eur"])
    mean_price = sum(h.price_eur for h in historical) / len(historical) if historical else list_price

    # The product's pet type, category and brand: from its latest sales
    # row, or from the catalogue when it has never sold.
    profile = sales[-1] if sales else product
    units_last_month = last_month_units(sales)

    def point(pct: int) -> CurvePoint:
        price = round(mean_price * (1.0 + pct / 100.0), 2)
        units = round(units_at_price(client, sku, profile, units_last_month, price, model="regression"), 2)
        return CurvePoint(price, units, round((price - unit_cost) * units, 2), pct)

    with ThreadPoolExecutor(max_workers=len(CURVE_ADJUSTMENTS_PCT)) as pool:
        curve = list(pool.map(point, CURVE_ADJUSTMENTS_PCT))

    centre = next(c for c in curve if c.adjustment_pct == 0)
    result = PriceCurve(
        sku=sku,
        name=product["name"],
        list_price_eur=round(list_price, 2),
        unit_cost_eur=round(unit_cost, 2),
        mean_price_eur=round(mean_price, 2),
        historical=historical,
        curve=curve,
        # The centre point's body, exactly as sent.
        last_query={"endpoint": "_estimate", "body": {
            "from": "monthly_sales",
            "where": price_where(sku, profile, units_last_month, centre.price_eur),
            "estimate": "units_sold",
            "model": "regression",
        }},
        last_response_ms=int((time.perf_counter() - started) * 1000),
    )
    cache.set(cache_key, result.to_dict(), ttl=1800)
    return result


def _from_dict(d: dict) -> PriceCurve:
    return PriceCurve(**{
        **d,
        "historical": [HistoricalPoint(**h) for h in d["historical"]],
        "curve": [CurvePoint(**c) for c in d["curve"]],
    })
