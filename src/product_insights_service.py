"""Product Insights — one product's funnel, surfaces, buyers, sales and reviews.

Five panels, all live against Aito (ADR 0028):

  1. Funnel      — impressions → clicked → added to cart → purchased
  2. Surfaces    — impressions and purchases per surface
  3. Who buys it — `_relate` over this product's order lines, one call
                   per customer column, in parallel
  4. Monthly     — `monthly_sales` rows for this product
  5. Reviews     — rating and sentiment counts

Panels 1, 2 and 5 are ~20 independent `_search limit: 0` counts. They go
in one `_batch`: one round-trip instead of twenty. The `_relate` calls are
fired in parallel instead, because `_batch` runs its items one after
another on the server.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

from src import cache
from src.aito_client import AitoClient, AitoError
from src.aito_compat import related_value
from src.bought_together_service import ANCHORS


DATA_DIR = Path(__file__).resolve().parent.parent / "data"

DEFAULT_SKU = "SKU-PT-0177"   # Puppy Cheese Treats: data in every panel (ADR 0028)

FUNNEL_STEPS: list[tuple[str, dict]] = [
    ("impressions",   {}),
    ("clicked",       {"clicked": True}),
    ("added_to_cart", {"added_to_cart": True}),
    ("purchased",     {"purchased": True}),
]
SURFACES = ["search", "for_you", "category", "bought_together"]
RATINGS = [1, 2, 3, 4, 5]
SENTIMENTS = ["positive", "neutral", "negative"]

# Customer columns denormalised onto order_lines, related to "bought this".
BUYER_FIELDS = [
    "customer_segment", "customer_pet_size", "customer_lifestyle",
    "customer_health_focus", "customer_treat_affinity", "customer_brand_loyalty",
]


class UnknownProductError(LookupError):
    """The requested SKU isn't in the catalog."""


@dataclass(frozen=True)
class FunnelStep:
    step: str
    count: int


@dataclass(frozen=True)
class SurfaceRow:
    surface: str
    impressions: int
    purchased: int


@dataclass(frozen=True)
class BuyerRow:
    field: str             # "customer_segment", ...
    value: str             # "dog_owner"
    lift: float            # share among this product's lines / share among all lines
    lines: int             # this product's order lines with this profile
    lines_total: int       # this product's order lines


@dataclass(frozen=True)
class MonthRow:
    month: str
    units_sold: int


@dataclass
class ProductInsights:
    product: dict
    funnel: list[FunnelStep]
    surfaces: list[SurfaceRow]
    buyers: list[BuyerRow]
    monthly: list[MonthRow]
    ratings: dict[str, int]          # "1".."5" → reviews
    sentiments: dict[str, int]       # "positive" … → reviews
    candidate_products: list[dict]   # the picker: sku, name, category, pet_type
    # Bought Together's anchor for this product's category, if it has one.
    bought_together_anchor: str | None
    last_query: dict

    def to_dict(self) -> dict:
        return asdict(self)


def load_catalog() -> dict[str, dict]:
    rows = json.loads((DATA_DIR / "products.json").read_text())
    return {p["sku"]: p for p in rows}


def buyers_relate_body(sku: str, field: str) -> dict:
    # Aito's `_relate`: with the product as the condition, each hit's lift
    # is how much more common `field`'s value is among this product's
    # order lines than among all order lines.
    return {"from": "order_lines", "where": {"product_sku": sku}, "relate": field}


def _count_queries(sku: str) -> list[dict]:
    def count(table: str, where: dict) -> dict:
        return {"from": table, "where": {"product_sku": sku, **where}, "limit": 0}

    return (
        [count("impressions", w) for _, w in FUNNEL_STEPS]
        + [count("impressions", {"surface": s}) for s in SURFACES]
        + [count("impressions", {"surface": s, "purchased": True}) for s in SURFACES]
        + [count("reviews", {"rating": r}) for r in RATINGS]
        + [count("reviews", {"sentiment": s}) for s in SENTIMENTS]
    )


def _counts(client: AitoClient, sku: str) -> tuple[list[FunnelStep], list[SurfaceRow], dict, dict]:
    totals = iter([res["total"] for res in client.batch(_count_queries(sku))])
    funnel = [FunnelStep(step, next(totals)) for step, _ in FUNNEL_STEPS]
    shown = [next(totals) for _ in SURFACES]
    bought = [next(totals) for _ in SURFACES]
    surfaces = [SurfaceRow(s, i, p) for s, i, p in zip(SURFACES, shown, bought)]
    ratings = {str(r): next(totals) for r in RATINGS}
    sentiments = {s: next(totals) for s in SENTIMENTS}

    # Every impression has exactly one surface, and every review a rating
    # and a sentiment. A mismatch means a value this view doesn't know.
    if sum(shown) != funnel[0].count:
        raise AitoError(f"{sku}: surfaces {SURFACES} cover {sum(shown)} of {funnel[0].count} impressions")
    if sum(ratings.values()) != sum(sentiments.values()):
        raise AitoError(f"{sku}: {sum(ratings.values())} reviews by rating but {sum(sentiments.values())} by sentiment")
    return funnel, surfaces, ratings, sentiments


def _buyer_rows(client: AitoClient, sku: str, field: str) -> list[BuyerRow]:
    body = buyers_relate_body(sku, field)
    hits = client.relate(table=body["from"], where=body["where"], relate_field=field, limit=10)["hits"]
    return [
        BuyerRow(
            field=field,
            value=str(related_value(hit, field)),
            lift=round(float(hit["lift"]), 2),
            lines=int(hit["fs"]["fOnCondition"]),
            lines_total=int(hit["fs"]["fCondition"]),
        )
        for hit in hits
    ]


def _monthly(client: AitoClient, sku: str) -> list[MonthRow]:
    res = client.search("monthly_sales", where={"product_sku": sku},
                        select=["month", "units_sold"], limit=200)
    units = {h["month"]: int(h["units_sold"]) for h in res["hits"]}
    if not units:
        return []
    # monthly_sales has a row only for months with sales, so a month with
    # no row sold 0 units. Fill them in so the chart's gaps are visible as
    # zeros; the page's caption says so.
    first, last = min(units), max(units)
    return [MonthRow(m, units.get(m, 0)) for m in _months_between(first, last)]


def _months_between(first: str, last: str) -> list[str]:
    year, month = map(int, first.split("-"))
    months = []
    while f"{year:04d}-{month:02d}" <= last:
        months.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def get_product_insights(client: AitoClient, sku: str | None = None) -> ProductInsights:
    catalog = load_catalog()
    sku = sku or DEFAULT_SKU
    if sku not in catalog:
        raise UnknownProductError(f"unknown product {sku!r}")

    cache_key = f"product-insights:{sku}"
    cached = cache.get(cache_key)
    if cached:
        return _from_dict(cached)

    with ThreadPoolExecutor(max_workers=len(BUYER_FIELDS) + 2) as pool:
        counts_job = pool.submit(_counts, client, sku)
        monthly_job = pool.submit(_monthly, client, sku)
        buyer_jobs = [pool.submit(_buyer_rows, client, sku, f) for f in BUYER_FIELDS]
        funnel, surfaces, ratings, sentiments = counts_job.result()
        monthly = monthly_job.result()
        buyers = [row for job in buyer_jobs for row in job.result()]

    product = catalog[sku]
    resp = ProductInsights(
        product={k: product[k] for k in ("sku", "name", "brand", "pet_type", "category", "price_eur")},
        funnel=funnel,
        surfaces=surfaces,
        buyers=sorted(buyers, key=lambda b: abs(b.lift - 1.0), reverse=True),
        monthly=monthly,
        ratings=ratings,
        sentiments=sentiments,
        candidate_products=[
            {k: p[k] for k in ("sku", "name", "category", "pet_type")}
            for p in sorted(catalog.values(), key=lambda p: (p["pet_type"], p["category"], p["name"]))
        ],
        bought_together_anchor=next(
            (a.anchor_id for a in ANCHORS if (a.pet_type, a.category) == (product["pet_type"], product["category"])),
            None,
        ),
        last_query={"endpoint": "_relate", "body": buyers_relate_body(sku, "customer_segment")},
    )
    cache.set(cache_key, resp.to_dict(), ttl=1800)
    return resp


def _from_dict(d: dict) -> ProductInsights:
    return ProductInsights(
        product=d["product"],
        funnel=[FunnelStep(**f) for f in d["funnel"]],
        surfaces=[SurfaceRow(**s) for s in d["surfaces"]],
        buyers=[BuyerRow(**b) for b in d["buyers"]],
        monthly=[MonthRow(**m) for m in d["monthly"]],
        ratings=d["ratings"],
        sentiments=d["sentiments"],
        candidate_products=d["candidate_products"],
        bought_together_anchor=d["bought_together_anchor"],
        last_query=d["last_query"],
    )
