"""Overview — "How is the shop doing, and where should I look?" (ADR 0041).

The owner's home: the shop's last 12 months against the 12 before, its
best sellers and its households, and the strongest basket pattern. The
headlines that point to each owner view are built on top of this at
request time (`src/overview_headlines.py`).

The Aito queries:

  1. `_search` over `orders` and `order_lines`, paged, with `select`:
     monthly orders and revenue, and units per product, are sums over
     every row, which `_search` returns and Python adds up. Two
     `limit: 0` counts give the customers and check the paging.
  2. Household cards: one `_batch` and five `_aggregate`s
     (`src/household_cards.py`).
  3. The basket section of Patterns (`src/basket_pairs.py`), whose
     strongest pair, with its interval, is the Patterns headline.

The result is precomputed (`./do precompute`, as `overview`), because it
is the landing view; live it takes a few seconds.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass

from src import cache
from src.aito_client import AitoClient, AitoError
from src.basket_pairs import get_basket_section
from src.household_cards import HouseholdCard, household_cards

PAGE = 5_000
TOP_PRODUCTS = 5
# Above the catalogue's 658 products: a full page raises.
PRODUCT_LIMIT = 2_000
ORDER_FIELDS = ["order_id", "customer_id", "month", "total_eur"]


@dataclass(frozen=True)
class MonthRow:
    month: str
    orders: int
    revenue_eur: float


@dataclass(frozen=True)
class Kpis:
    first_month: str               # the last 12 months: first_month … last_month
    last_month: str
    orders: int
    orders_before: int             # the 12 months before
    months_before: int             # how many of those 12 the data holds
    revenue_eur: float
    revenue_before_eur: float
    avg_basket_eur: float
    customers_ordering: int        # customers with an order in the 12 months
    customers: int                 # every customer
    products: int


@dataclass(frozen=True)
class TopProduct:
    sku: str
    name: str
    pet_type: str
    category: str
    units: int                     # in the last 12 months


@dataclass
class OverviewResponse:
    kpis: Kpis
    monthly: list[MonthRow]        # every month in the data, oldest first
    top_products: list[TopProduct]
    households: list[HouseholdCard]
    top_basket_pair: dict          # Patterns' strongest pair (a BasketPair)
    basket_significance: dict
    last_query: dict

    def to_dict(self) -> dict:
        return asdict(self)


def all_rows(client: AitoClient, table: str, select: list[str]) -> list[dict]:
    """Every row of `table`, a page at a time; raises if the pages don't
    add up to the table's count."""
    rows: list[dict] = []
    while True:
        page = client.search(table, limit=PAGE, offset=len(rows), select=select)
        rows += page["hits"]
        if len(page["hits"]) < PAGE:
            break
    total = client.search(table, limit=0)["total"]
    if len(rows) != total:
        raise AitoError(f"{table}: paged {len(rows)} rows, the table holds {total}")
    return rows


def months_back(month: str, months: int) -> str:
    """`months_back("2026-04", 12)` → `"2025-04"`."""
    year, number = (int(x) for x in month.split("-"))
    total = year * 12 + number - 1 - months
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def shop_totals(orders: list[dict]) -> tuple[list[MonthRow], dict]:
    """Monthly orders and revenue, and the last 12 months against the 12 before."""
    count: Counter[str] = Counter()
    revenue: dict[str, float] = defaultdict(float)
    for o in orders:
        count[o["month"]] += 1
        revenue[o["month"]] += float(o["total_eur"])
    monthly = [MonthRow(m, count[m], round(revenue[m], 2)) for m in sorted(count)]

    last = monthly[-1].month
    first, before = months_back(last, 11), months_back(last, 23)
    recent = [m for m in monthly if m.month >= first]
    earlier = [m for m in monthly if before <= m.month < first]
    orders_recent = sum(m.orders for m in recent)
    revenue_recent = sum(m.revenue_eur for m in recent)
    return monthly, {
        "first_month": first, "last_month": last,
        "orders": orders_recent, "orders_before": sum(m.orders for m in earlier), "months_before": len(earlier),
        "revenue_eur": round(revenue_recent, 2),
        "revenue_before_eur": round(sum(m.revenue_eur for m in earlier), 2),
        "avg_basket_eur": round(revenue_recent / orders_recent, 2),
        "customers_ordering": len({o["customer_id"] for o in orders if o["month"] >= first}),
    }


def top_products(lines: list[dict], month_of_order: dict[str, str], first_month: str,
                 products: dict[str, dict]) -> list[TopProduct]:
    """The products with the most units sold since `first_month`."""
    units: Counter[str] = Counter()
    for line in lines:
        if month_of_order[line["order_id"]] >= first_month:
            units[line["product_sku"]] += int(line["qty"])
    out = []
    for sku, n in units.most_common(TOP_PRODUCTS):
        p = products[sku]
        out.append(TopProduct(sku, p["name"], p["pet_type"], p["category"], n))
    return out


def _compute(client: AitoClient) -> OverviewResponse:
    orders = all_rows(client, "orders", ORDER_FIELDS)
    lines = all_rows(client, "order_lines", ["order_id", "product_sku", "qty"])
    catalogue = client.search("products", limit=PRODUCT_LIMIT, select=["sku", "name", "pet_type", "category"])
    if len(catalogue["hits"]) != catalogue["total"]:
        raise AitoError(f"products: read {len(catalogue['hits'])} of {catalogue['total']}")
    customers = client.search("customers", limit=0)["total"]

    monthly, totals = shop_totals(orders)
    month_of_order = {o["order_id"]: o["month"] for o in orders}
    products = {p["sku"]: p for p in catalogue["hits"]}
    baskets = get_basket_section(client)
    together = [p for p in baskets.pairs if p.lift > 1]
    if not together:
        raise AitoError("no basket pair clears the significance bar above 1; the Patterns headline has nothing to say")

    return OverviewResponse(
        kpis=Kpis(**totals, customers=customers, products=catalogue["total"]),
        monthly=monthly,
        top_products=top_products(lines, month_of_order, totals["first_month"], products),
        households=household_cards(client, total_customers=customers),
        top_basket_pair=asdict(together[0]),
        basket_significance=asdict(baskets.significance),
        last_query={"endpoint": "_search",
                    "body": {"from": "orders", "limit": PAGE, "offset": 0, "select": ORDER_FIELDS}},
    )


def get_overview(client: AitoClient) -> dict:
    """The Overview payload, cached for 10 minutes when not precomputed."""
    return cache.get_or_compute("overview", lambda: _compute(client).to_dict(), ttl=600)
