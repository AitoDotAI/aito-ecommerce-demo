"""Purchase Analytics — read-heavy aggregations powered by `_search`.

The "show the data behind the predictions" view. Four blocks:
  - Monthly orders/revenue (24-month window)
  - Top 10 products by line count
  - Per-segment KPIs (customers, orders, revenue, AOV)
  - Per-segment top categories

No new Aito mechanics; reuses `_search limit=0` for counts +
small samples + Python aggregation. Cached 30 minutes.
"""

from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path

from src.aito_client import AitoClient
from src import cache


DATA_DIR = Path(__file__).resolve().parent.parent / "data"


# ── Segment metadata (label only — full meta lives in overview) ────


_SEGMENT_LABELS: dict[str, str] = {
    "dog_owner":          "Dog owners",
    "cat_owner":          "Cat owners",
    "multi_pet":          "Multi-pet households",
    "small_animal_owner": "Small animals",
    "aquarium_owner":     "Aquarium / exotic",
}


# ── DTOs ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class MonthlyRow:
    month: str
    orders: int
    revenue_eur: float


@dataclass(frozen=True)
class TopProduct:
    sku: str
    name: str
    pet_type: str
    category: str
    line_count: int


@dataclass(frozen=True)
class SegmentRow:
    segment: str
    label: str
    customers: int
    orders: int
    revenue_eur: float
    avg_basket_eur: float


@dataclass(frozen=True)
class CategoryMix:
    pet_type: str
    category: str
    count: int
    share_pct: float


@dataclass(frozen=True)
class CategoryMixRow:
    segment: str
    label: str
    top_categories: list[CategoryMix]


@dataclass
class AnalyticsResponse:
    monthly: list[MonthlyRow]
    top_products: list[TopProduct]
    segments: list[SegmentRow]
    category_mix_by_segment: list[CategoryMixRow]
    last_query: dict
    last_response_ms: int

    def to_dict(self) -> dict:
        return {
            "monthly":      [asdict(m) for m in self.monthly],
            "top_products": [asdict(t) for t in self.top_products],
            "segments":     [asdict(s) for s in self.segments],
            "category_mix_by_segment": [
                {**asdict(r), "top_categories": [asdict(c) for c in r.top_categories]}
                for r in self.category_mix_by_segment
            ],
            "last_query":       self.last_query,
            "last_response_ms": self.last_response_ms,
        }


# ── Local catalog (fast lookup for top-products names) ─────────────


def _load_products() -> dict[str, dict]:
    rows = json.loads((DATA_DIR / "products.json").read_text())
    return {p["sku"]: p for p in rows}


# ── Aggregations ───────────────────────────────────────────────────


def _monthly_orders(client: AitoClient) -> list[MonthlyRow]:
    """Pull all orders (paged) and aggregate per month locally. Aito's
    `_search` returns ~12 k orders comfortably in two pages."""
    monthly_counts: Counter[str] = Counter()
    monthly_revenue: dict[str, float] = defaultdict(float)
    offset = 0
    page = 5000
    while True:
        res = client.search("orders", limit=page, offset=offset)
        hits = res.get("hits", [])
        if not hits:
            break
        for o in hits:
            m = o.get("month", "")
            monthly_counts[m] += 1
            monthly_revenue[m] += float(o.get("total_eur", 0) or 0)
        if len(hits) < page:
            break
        offset += page
    months = sorted(monthly_counts)
    return [
        MonthlyRow(month=m, orders=monthly_counts[m], revenue_eur=round(monthly_revenue[m], 2))
        for m in months
    ]


def _top_products(client: AitoClient, products: dict[str, dict]) -> list[TopProduct]:
    counts: Counter[str] = Counter()
    offset = 0
    page = 5000
    while True:
        res = client.search("order_lines", limit=page, offset=offset)
        hits = res.get("hits", [])
        if not hits:
            break
        for ln in hits:
            counts[ln.get("product_sku", "")] += 1
        if len(hits) < page:
            break
        offset += page
    out: list[TopProduct] = []
    for sku, count in counts.most_common(10):
        prod = products.get(sku)
        if not prod:
            continue
        out.append(TopProduct(
            sku=sku,
            name=prod.get("name", ""),
            pet_type=prod.get("pet_type", ""),
            category=prod.get("category", ""),
            line_count=count,
        ))
    return out


def _segment_kpis(client: AitoClient) -> tuple[list[SegmentRow], list[CategoryMixRow], dict[str, str]]:
    """One pass over customers + orders + order_lines to compute
    per-segment KPIs + category mix."""
    products = _load_products()

    # Customer map.
    customers_by_id: dict[str, dict] = {}
    offset = 0
    page = 3000
    while True:
        res = client.search("customers", limit=page, offset=offset)
        hits = res.get("hits", [])
        if not hits:
            break
        for c in hits:
            customers_by_id[c["customer_id"]] = c
        if len(hits) < page:
            break
        offset += page

    # Orders → segment + total.
    seg_orders: Counter[str] = Counter()
    seg_revenue: dict[str, float] = defaultdict(float)
    seg_customers_seen: dict[str, set[str]] = defaultdict(set)
    order_to_segment: dict[str, str] = {}
    offset = 0
    while True:
        res = client.search("orders", limit=page, offset=offset)
        hits = res.get("hits", [])
        if not hits:
            break
        for o in hits:
            cust = customers_by_id.get(o.get("customer_id", ""))
            if not cust:
                continue
            seg = cust.get("segment", "")
            if not seg:
                continue
            seg_orders[seg] += 1
            seg_revenue[seg] += float(o.get("total_eur", 0) or 0)
            seg_customers_seen[seg].add(cust["customer_id"])
            order_to_segment[o["order_id"]] = seg
        if len(hits) < page:
            break
        offset += page

    # Lines → segment × (pet_type, category) for the mix.
    seg_cat_counts: dict[str, Counter[tuple[str, str]]] = defaultdict(Counter)
    offset = 0
    while True:
        res = client.search("order_lines", limit=page, offset=offset)
        hits = res.get("hits", [])
        if not hits:
            break
        for ln in hits:
            seg = order_to_segment.get(ln.get("order_id", ""))
            if not seg:
                continue
            prod = products.get(ln.get("product_sku", ""))
            if not prod:
                continue
            seg_cat_counts[seg][(prod.get("pet_type", ""), prod.get("category", ""))] += 1
        if len(hits) < page:
            break
        offset += page

    # Build SegmentRow + CategoryMixRow lists.
    seg_total_customers: Counter[str] = Counter()
    for c in customers_by_id.values():
        seg = c.get("segment", "")
        if seg:
            seg_total_customers[seg] += 1

    segments: list[SegmentRow] = []
    for seg, label in _SEGMENT_LABELS.items():
        orders = seg_orders.get(seg, 0)
        revenue = seg_revenue.get(seg, 0.0)
        avg = revenue / orders if orders else 0.0
        segments.append(SegmentRow(
            segment=seg,
            label=label,
            customers=seg_total_customers.get(seg, 0),
            orders=orders,
            revenue_eur=round(revenue, 2),
            avg_basket_eur=round(avg, 2),
        ))

    mix: list[CategoryMixRow] = []
    for seg, label in _SEGMENT_LABELS.items():
        counter = seg_cat_counts.get(seg, Counter())
        total = sum(counter.values()) or 1
        top = [
            CategoryMix(
                pet_type=pair[0],
                category=pair[1],
                count=count,
                share_pct=round(count / total * 100, 1),
            )
            for pair, count in counter.most_common(5)
        ]
        mix.append(CategoryMixRow(segment=seg, label=label, top_categories=top))

    return segments, mix, order_to_segment


# ── Public entry point ────────────────────────────────────────────


def get_analytics(client: AitoClient) -> AnalyticsResponse:
    cached = cache.get("analytics:summary")
    if cached:
        return _from_dict(cached)

    body = {
        "from": "orders",
        "where": {},
        "limit": 5000,
        # Sample paged through Aito's `_search` and aggregated client-side.
    }

    started = time.perf_counter()
    products = _load_products()
    monthly = _monthly_orders(client)
    top_products = _top_products(client, products)
    segments, mix, _ = _segment_kpis(client)
    elapsed = int((time.perf_counter() - started) * 1000)

    resp = AnalyticsResponse(
        monthly=monthly,
        top_products=top_products,
        segments=segments,
        category_mix_by_segment=mix,
        last_query={"endpoint": "_search", "body": body},
        last_response_ms=elapsed,
    )
    cache.set("analytics:summary", resp.to_dict(), ttl=1800)
    return resp


# ── Cache round-trip ──────────────────────────────────────────────


def _from_dict(d: dict) -> AnalyticsResponse:
    return AnalyticsResponse(
        monthly=[MonthlyRow(**m) for m in d["monthly"]],
        top_products=[TopProduct(**t) for t in d["top_products"]],
        segments=[SegmentRow(**s) for s in d["segments"]],
        category_mix_by_segment=[
            CategoryMixRow(
                segment=r["segment"],
                label=r["label"],
                top_categories=[CategoryMix(**c) for c in r["top_categories"]],
            )
            for r in d["category_mix_by_segment"]
        ],
        last_query=d["last_query"],
        last_response_ms=d["last_response_ms"],
    )
