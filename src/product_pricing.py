"""A product's list price and what it would do: the Product view's Pricing tab (ADR 0050).

The owner types a list price; the page shows the units and profit that price gives next to the product's
own months. Units come from one `_estimate units_index` per price (the regression, with the product and the
price in the `where`), times the product's mean units before the month. `units_index` is relative to the
product's own history, so the same slope does not apply to a 1-unit and a 27-unit product alike (ADR 0049).

A price the product has not been sold near is not answered with a number: the estimate extrapolates a line,
and a profit-maximising price outside the data would only be the end of the axis. `in_range` says whether
the effective price index lies within the product's own months' (plus RANGE_MARGIN), and the best price is
picked among those only.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass

from src.aito_client import AitoClient, AitoError
from src.demand_forecast import LATEST_MONTH
from src.lookup_errors import ProductNotOnSaleError, UnknownProductError
from src.timing import submit_in_request

# The curve spans the list price index of ADR 0049's price points, which the data holds for dynamic products.
CURVE_INDEXES = (0.85, 0.90, 0.95, 1.00, 1.05, 1.10, 1.15)
RANGE_MARGIN = 0.05     # how far beyond its tried prices a product's estimate is still answered


@dataclass(frozen=True)
class PricePoint:
    list_price_eur: float
    list_price_index: float     # the list price against the product's reference list price
    price_eur: float            # what a shopper pays: the list price less the month's offer
    price_index: float          # ... against the reference list price (monthly_sales.price_index)
    units_index: float          # Aito's estimate, floored at 0
    units: float
    revenue_eur: float
    profit_eur: float
    in_range: bool              # the product has been sold at about this price


@dataclass(frozen=True)
class OwnMonth:
    month: str
    price_index: float
    units: int
    units_index: float | None


@dataclass(frozen=True)
class ProductPricing:
    sku: str
    name: str
    month: str
    reference_list_eur: float   # the list price the indexes are against: the product's first
    list_price_eur: float       # its list price in `month`
    unit_cost_eur: float
    offer_pct: float            # the month's offer, applied to every price on the page
    mean_units: float | None    # units a month before `month`: what an index of 1.0 means; None: never sold
    tried_from: float           # the lowest and highest effective price index among its own months
    tried_to: float
    asked: PricePoint | None
    best: PricePoint | None     # the most profit among the curve's in-range prices
    curve: list[PricePoint]
    own_months: list[OwnMonth]
    last_query: dict

    def to_dict(self) -> dict:
        return asdict(self)


def estimate_body(sku: str, price_index: float) -> dict:
    return {"from": "monthly_sales", "where": {"product_sku": sku, "price_index": price_index},
            "estimate": "units_index", "model": "regression"}


def get_product_pricing(client: AitoClient, sku: str, month: str = LATEST_MONTH,
                        list_price_eur: float | None = None) -> ProductPricing:
    products = client.search("products", where={"sku": sku}, limit=1)["hits"]
    if not products:
        raise UnknownProductError(f"No product {sku} in the catalogue")
    states = client.search("product_states", where={"product_sku": sku, "month": month}, limit=1)["hits"]
    if not states:
        raise ProductNotOnSaleError(f"{sku} has no state in {month}")
    state = states[0]
    inventory = client.search("inventory", where={"sku": sku}, limit=1)["hits"]
    if not inventory:
        raise AitoError(f"{sku} has no inventory row, so it has no unit cost")
    sales = sorted(client.search("monthly_sales", where={"product_sku": sku}, limit=200)["hits"],
                   key=lambda r: r["month"])
    if not sales:
        raise AitoError(f"{sku} has no monthly sales, so its prices have no data to be read from")

    reference = round(float(state["list_price_eur"]) / float(state["list_price_index"]), 2)
    offer = float(state["discount_pct"]) if state["on_offer"] else 0.0
    unit_cost = float(inventory[0]["unit_cost_eur"])
    earlier = [r["units_sold"] for r in sales if r["month"] < month]
    mean_units = sum(earlier) / len(earlier) if earlier and sum(earlier) else None
    indexes = [float(r["price_index"]) for r in sales]
    tried_from, tried_to = min(indexes), max(indexes)

    asked_index = None if list_price_eur is None else list_price_eur / reference
    grid = sorted({*CURVE_INDEXES, *([round(asked_index, 3)] if asked_index is not None else [])})
    effective = [round(i * (1 - offer / 100), 3) for i in grid]
    if mean_units is None:
        estimates = [None] * len(grid)
    else:
        with ThreadPoolExecutor(max_workers=len(grid)) as pool:
            jobs = [submit_in_request(pool, estimate_units_index, client, sku, e) for e in effective]
            estimates = [job.result() for job in jobs]

    points = [point(i, e, est, reference, offer, unit_cost, mean_units, tried_from, tried_to)
              for i, e, est in zip(grid, effective, estimates)]
    asked = next((p for p in points if asked_index is not None and p.list_price_index == round(asked_index, 3)), None)
    curve = [p for p in points if p.list_price_index in CURVE_INDEXES]
    answered = [p for p in curve if p.in_range and mean_units is not None]
    return ProductPricing(
        sku=sku, name=products[0]["name"], month=month, reference_list_eur=reference,
        list_price_eur=float(state["list_price_eur"]), unit_cost_eur=round(unit_cost, 2), offer_pct=offer,
        mean_units=None if mean_units is None else round(mean_units, 2), tried_from=tried_from, tried_to=tried_to,
        asked=asked, best=max(answered, key=lambda p: p.profit_eur) if answered else None, curve=curve,
        own_months=[OwnMonth(r["month"], float(r["price_index"]), int(r["units_sold"]), r.get("units_index"))
                    for r in sales],
        last_query={"endpoint": "_estimate", "body": estimate_body(sku, effective[len(grid) // 2])},
    )


def estimate_units_index(client: AitoClient, sku: str, price_index: float) -> float:
    """Aito's `_estimate units_index` for the product at an effective price index, floored at 0
    (a line can go below zero at a high price; units cannot)."""
    body = estimate_body(sku, price_index)
    answer = client.estimate(body["from"], body["where"], "units_index", model="regression", with_why=False)
    if answer.get("estimate") is None:
        raise AitoError(f"_estimate units_index returned no estimate for {sku} at price index {price_index}: {answer}")
    return max(float(answer["estimate"]), 0.0)


def point(list_index: float, price_index: float, estimate: float | None, reference: float, offer_pct: float,
          unit_cost: float, mean_units: float | None, tried_from: float, tried_to: float) -> PricePoint:
    list_price = round(reference * list_index, 2)
    price = round(list_price * (1 - offer_pct / 100), 2)
    units_index = 0.0 if estimate is None else estimate
    units = 0.0 if mean_units is None else units_index * mean_units
    return PricePoint(
        list_price_eur=list_price, list_price_index=list_index, price_eur=price, price_index=price_index,
        units_index=round(units_index, 3), units=round(units, 2), revenue_eur=round(units * price, 2),
        profit_eur=round(units * (price - unit_cost), 2),
        in_range=tried_from - RANGE_MARGIN <= price_index <= tried_to + RANGE_MARGIN,
    )
