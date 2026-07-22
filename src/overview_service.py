"""Dashboard data layer — `/api/dashboard`.

Composes the four blocks the Dashboard view shows:
  1. KPI grid    — live `_search` counts.
  2. Top patterns — Python-side co-occurrence lift over local fixtures.
  3. Segments    — live `_search` counts per segment + avg-basket aggs.
  4. Recent orders — live `_search` over orders, no per-row predictions
                    (those land with the For You / Bought Together views).

See `docs/adr/0005-dashboard.md` for the why of the live/local split.
The same `DashboardResponse` shape is consumed by
`frontend/app/page.tsx`; keep the field names in lock-step.
"""

from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from src.aito_client import AitoClient
from src import cache


DATA_DIR = Path(__file__).resolve().parent.parent / "data"


# ── DTOs ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Kpi:
    value: float
    delta_label: str | None


@dataclass(frozen=True)
class Kpis:
    products: Kpi
    orders_12mo: Kpi
    customers: Kpi
    avg_basket_eur: Kpi


@dataclass(frozen=True)
class Pattern:
    label: str
    lift: float
    bar_pct: float


@dataclass(frozen=True)
class SegmentCard:
    id: str
    emoji: str
    label: str
    share_pct: float
    avg_basket_eur: float
    note: str
    pill_text: str
    pill_tone: str


@dataclass(frozen=True)
class Insight:
    headline: str
    body: str


@dataclass(frozen=True)
class RecentOrder:
    order_id: str
    customer_short: str   # first name only
    month: str
    line_summary: str
    total_eur: float


@dataclass
class DashboardResponse:
    kpis: Kpis
    top_patterns: list[Pattern]
    segments: list[SegmentCard]
    insight: Insight
    recent_orders: list[RecentOrder]
    last_query: dict
    last_response_ms: int

    def to_dict(self) -> dict:
        return {
            "kpis": {
                "products":       asdict(self.kpis.products),
                "orders_12mo":    asdict(self.kpis.orders_12mo),
                "customers":      asdict(self.kpis.customers),
                "avg_basket_eur": asdict(self.kpis.avg_basket_eur),
            },
            "top_patterns":  [asdict(p) for p in self.top_patterns],
            "segments":      [asdict(s) for s in self.segments],
            "insight":       asdict(self.insight),
            "recent_orders": [asdict(o) for o in self.recent_orders],
            "last_query":    self.last_query,
            "last_response_ms": self.last_response_ms,
        }


# ── Segment metadata (fixed tone / emoji / note per segment) ───────


_SEGMENT_META: dict[str, dict[str, str]] = {
    "dog_owner": {
        "emoji": "🐕", "label": "Dog owners",
        "note":  "monthly food reorder · highest LTV",
        "pill_text": "Highest LTV", "pill_tone": "orange",
    },
    "cat_owner": {
        "emoji": "🐈", "label": "Cat owners",
        "note":  "bi-weekly litter · steady frequency",
        "pill_text": "High frequency", "pill_tone": "blue",
    },
    "multi_pet": {
        "emoji": "🐾", "label": "Multi-pet households",
        "note":  "dog + cat · cross-sell sweet spot",
        "pill_text": "Cross-sell", "pill_tone": "purple",
    },
    "small_animal_owner": {
        "emoji": "🐹", "label": "Small animals",
        "note":  "weekly bedding · growing segment",
        "pill_text": "Growing", "pill_tone": "grey",
    },
    "aquarium_owner": {
        "emoji": "🐟", "label": "Aquarium / exotic",
        "note":  "monthly · high AOV",
        "pill_text": "High AOV", "pill_tone": "purple",
    },
}


# ── Top patterns — Python-side lift over the fixture data ──────────


def _load_local_data() -> tuple[list[dict], list[dict], list[dict]]:
    """Read the three on-disk fixtures the top-patterns computation
    needs. Cached at module level for the process lifetime —
    fixtures are immutable between regens."""
    return (
        json.loads((DATA_DIR / "products.json").read_text()),
        json.loads((DATA_DIR / "orders.json").read_text()),
        json.loads((DATA_DIR / "order_lines.json").read_text()),
    )


# Each pattern is `((pet_a, cat_a), (pet_b, cat_b))` with a label.
# The pet_type-qualified anchor matters: dog dry-food's dental-treats
# lift is engineered to ~3×, but cat dry-food's isn't — averaging
# both into one "dry-food → dental-treats" bucket would dilute the
# signal to ~1.5×. See ADR 0002 §Engineered signal #2.
_PATTERN_PAIRS: list[tuple[tuple[str, str], tuple[str, str], str]] = [
    (("dog", "dry-food"), ("dog", "dental-treats"),
     "Dog dry-food → Dental treats"),
    (("dog", "dry-food"), ("dog", "treats"),
     "Dog dry-food → Dog treats"),
    (("dog", "dry-food"), ("dog", "accessories"),
     "Dog dry-food → Dog accessories"),
    (("cat", "wet-food"), ("cat", "litter"),
     "Cat wet-food → Cat litter"),
    (("cat", "dry-food"), ("cat", "wet-food"),
     "Cat dry-food → Cat wet-food"),
    (("aquarium", "aquarium"), ("aquarium", "health"),
     "Aquarium food → Aquarium health"),
]


def _compute_top_patterns(client: AitoClient, k: int = 6) -> list[Pattern]:
    """Order-level co-occurrence lift via live `_relate`.

    For each curated `(pet_a, cat_a) → (pet_b, cat_b)` pattern in
    `_PATTERN_PAIRS`, runs the same query Bought Together uses:

      _relate from orders where {line_categories: $match <anchor>}
              relate line_categories

    and reads the target's lift off the response. See ADR 0008 for
    the `orders.line_categories` denormalisation rationale.

    Six anchors → six parallel `_relate` calls. Cached at the
    `get_dashboard` level (10 min); inner anchors aren't cached
    separately because Pattern Explorer / Bought Together hit the
    same query body with their own cache keys.

    The pair list stays curated (not strict sort-by-lift): aquarium
    → aquarium niche pattern inflates lift to ≈ 16× because of its
    low base rate, mathematically correct but visually misleading
    for the dashboard's narrative. Pattern Explorer is the right
    place for raw-ranked discovery.
    """
    anchors_targets: list[tuple[str, str, str, str]] = []
    for (anchor_pet, anchor_cat), (target_pet, target_cat), label in _PATTERN_PAIRS:
        anchor_token = f"{anchor_pet}_{anchor_cat.replace('-', '')}"
        target_token = f"{target_pet}_{target_cat.replace('-', '')}"
        anchors_targets.append((anchor_token, target_token, label, anchor_pet))

    def _lift_for(anchor_token: str, target_token: str) -> float | None:
        try:
            res = client.relate(
                table="orders",
                where={"line_categories": {"$match": anchor_token}},
                relate_field="line_categories",
                limit=20,
            )
        except Exception:
            return None
        for hit in res.get("hits", []):
            rel = hit.get("related", {}).get("line_categories", {})
            token = rel.get("$has") if isinstance(rel, dict) else None
            if token == target_token:
                return float(hit.get("lift", 0))
        return None

    with ThreadPoolExecutor(max_workers=min(6, len(anchors_targets))) as pool:
        lifts = list(pool.map(
            lambda t: _lift_for(t[0], t[1]),
            anchors_targets,
        ))

    out: list[Pattern] = []
    for (anchor_token, target_token, label, _pet), lift in zip(anchors_targets, lifts):
        if lift is None or lift == 0:
            continue
        bar_pct = min(1.0, lift / 3.5) * 100
        out.append(Pattern(
            label=label,
            lift=round(lift, 2),
            bar_pct=round(bar_pct, 1),
        ))

    return out[:k]


# ── Live Aito calls — KPI / segment counts + recent orders ─────────


def _kpi_counts(client: AitoClient, *, today_yyyymm: str) -> tuple[Kpis, dict, int]:
    """Run the four KPI `_search limit=0` calls and one aggregate.

    Returns the Kpis dataclass + the last-query body + elapsed ms.
    The 12-month window cuts off 12 months back from `today_yyyymm`.
    """
    started = time.perf_counter()

    products_total = client.search("products", limit=0)["total"]
    customers_total = client.search("customers", limit=0)["total"]

    # 12-month cutoff. Strings sort lexicographically when in YYYY-MM
    # form, so $gte works directly without date parsing.
    cutoff = _month_minus(today_yyyymm, 12)
    orders_q_body: dict[str, Any] = {
        "from": "orders",
        "where": {"month": {"$gte": cutoff}},
        "limit": 0,
    }
    orders_12mo = client.search(
        "orders",
        where=orders_q_body["where"],
        limit=0,
    )["total"]

    # Avg basket — read total_eur off a window of recent orders. Aito
    # doesn't expose a SUM aggregation directly; we pull a large
    # limit (cheap on the 12k-row table) and average locally.
    sample = client.search(
        "orders",
        where={"month": {"$gte": cutoff}},
        limit=2000,  # enough rows for a stable average
    )
    totals = [o.get("total_eur", 0) for o in sample.get("hits", [])]
    avg_basket = round(sum(totals) / len(totals), 2) if totals else 0.0

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    kpis = Kpis(
        products=Kpi(value=products_total, delta_label=None),
        orders_12mo=Kpi(value=orders_12mo, delta_label=None),
        customers=Kpi(value=customers_total, delta_label=None),
        avg_basket_eur=Kpi(value=avg_basket, delta_label=None),
    )
    return kpis, orders_q_body, elapsed_ms


def _month_minus(yyyymm: str, months: int) -> str:
    year, month = (int(x) for x in yyyymm.split("-"))
    total = year * 12 + (month - 1) - months
    new_year, new_month = divmod(total, 12)
    return f"{new_year:04d}-{new_month + 1:02d}"


def _segment_cards(client: AitoClient, *, total_customers: int) -> list[SegmentCard]:
    """One card per customer segment: population share + average basket.

    Two Aito shapes, both server-side — no per-row fan-out:

      1. **Customer counts** for every segment in a single `_batch`
         (one round-trip for all five `_search limit=0` counts).
      2. **Average basket** per segment via one `_aggregate` on the
         `customers` table, which carries `segment` natively (no link
         traversal) plus per-customer `total_spent_eur` / `total_orders`.
         `mean(total_spent_eur) / mean(total_orders)` is algebraically
         the exact order-weighted mean basket for the segment
         (`Σspend / Σorders`), and — because `segment` needs no join and
         `customers` is small — it costs ~20 ms server-side vs ~2.9 s for
         the equivalent link-filtered aggregate over `orders`.

    This replaced an N+1 anti-pattern (sample 60 customers × one
    `_search` each for their orders = ~300 sequential round-trips). The
    round-trips, not Aito's ~2 ms/query, were the dashboard's whole cold
    cost. See ADR 0024.
    """
    seg_ids = list(_SEGMENT_META.keys())

    # 1) All per-segment customer counts in one request.
    counts = client.batch([
        {"from": "customers", "where": {"segment": seg_id}, "limit": 0}
        for seg_id in seg_ids
    ])

    cards: list[SegmentCard] = []
    for seg_id, count_res in zip(seg_ids, counts):
        seg_total = count_res["total"]
        if seg_total == 0:
            continue

        # 2) Exact mean basket, aggregated on `customers` (segment is a
        #    native column — no `orders` join).
        agg = client.aggregate(
            table="customers",
            where={"segment": seg_id},
            aggregate_fields=["total_spent_eur.$mean", "total_orders.$mean"],
        )
        mean_spent = agg.get("total_spent_eur.$mean") or 0.0
        mean_orders = agg.get("total_orders.$mean") or 0.0
        avg_basket = round(mean_spent / mean_orders, 2) if mean_orders else 0.0

        meta = _SEGMENT_META[seg_id]
        share_pct = round(seg_total / max(1, total_customers) * 100, 1)
        cards.append(SegmentCard(
            id=seg_id,
            emoji=meta["emoji"],
            label=meta["label"],
            share_pct=share_pct,
            avg_basket_eur=avg_basket,
            note=meta["note"],
            pill_text=meta["pill_text"],
            pill_tone=meta["pill_tone"],
        ))
    return cards


_FIRST_NAMES = [
    "Mikko", "Sari", "Antti", "Maija", "Olli", "Saara", "Liisa", "Janne",
    "Heidi", "Pekka", "Maria", "Joonas", "Erika", "Henrik", "Petra",
]


def _short_customer_name(customer_id: str) -> str:
    """Deterministic anonymous label per customer_id. Picks a Finnish
    first name + last-initial so the table reads like a real shop's
    recent-orders panel without leaking actual identities."""
    # Hash the id deterministically so the same customer always gets
    # the same display name.
    h = sum(ord(c) for c in customer_id)
    first = _FIRST_NAMES[h % len(_FIRST_NAMES)]
    initial = chr(ord("A") + ((h // 7) % 26))
    return f"{first} {initial}."


def _recent_orders(client: AitoClient, products: list[dict], limit: int = 6) -> list[RecentOrder]:
    """Most-recent orders by month. The `_search` `orderBy` form ranks
    by the supplied scalar value descending — month strings sort
    lexicographically in YYYY-MM form so this works without date
    parsing."""
    sku_to_name: dict[str, str] = {p["sku"]: p["name"] for p in products}

    orders = client.search(
        "orders",
        order_by={"$desc": "month"},
        limit=limit,
    ).get("hits", [])

    # Pull every order's lines in one `_batch` instead of one `_search`
    # per order — the same round-trip collapse as the segment counts.
    line_results = client.batch([
        {"from": "order_lines", "where": {"order_id": o["order_id"]}, "limit": 10}
        for o in orders
    ]) if orders else []

    out: list[RecentOrder] = []
    for o, lines_res in zip(orders, line_results):
        lines = lines_res.get("hits", [])
        names = [
            sku_to_name.get(ln["product_sku"], ln["product_sku"])
            for ln in lines
        ]
        if not names:
            summary = "(empty order)"
        elif len(names) == 1:
            summary = names[0]
        else:
            summary = f"{names[0]} + {len(names) - 1} more"

        out.append(RecentOrder(
            order_id=o["order_id"],
            customer_short=_short_customer_name(o["customer_id"]),
            month=o["month"],
            line_summary=summary,
            total_eur=round(float(o.get("total_eur", 0)), 2),
        ))
    return out


_INSIGHT_ANCHOR_LABEL = "Dog dry-food → Dental treats"


def _build_insight(patterns: list[Pattern]) -> Insight:
    """One-line tip-box headline using the **narrative** anchor
    pattern, not the highest-lift one.

    Aquarium → aquarium-health lifts ≈ 17× because aquarium orders
    are a closed niche (small denominator), which is mathematically
    correct but visually overpowers the dog → dental-treats moment
    that the rest of the demo (Bought Together, customer-switcher
    walkthrough) builds on. The dashboard surfaces every pattern
    in the table; the tip-box leads with the load-bearing one.
    """
    if not patterns:
        return Insight(
            headline="Insight",
            body="Top patterns will populate once Bought Together is wired live.",
        )
    anchor = next(
        (p for p in patterns if p.label == _INSIGHT_ANCHOR_LABEL),
        patterns[0],
    )
    return Insight(
        headline="Insight",
        body=(
            f"<strong>{anchor.label}</strong> co-occurs at "
            f"<strong>{anchor.lift:.2f}×</strong> baseline — Aito flags this as "
            f"the demo's headline cross-sell signal. Drill into individual SKU "
            f"pairs on Bought Together; live-rank the pattern's customer "
            f"segments on Pattern Explorer."
        ),
    )


# ── Public entry point ────────────────────────────────────────────


def get_dashboard(
    client: AitoClient,
    *,
    today_yyyymm: str = "2026-04",
) -> DashboardResponse:
    """Compose the full Dashboard payload. Cached for 10 minutes."""

    cached: dict | None = cache.get("dashboard:summary")
    if cached:
        return _from_dict(cached)

    kpis, kpi_query, kpi_ms = _kpi_counts(client, today_yyyymm=today_yyyymm)
    patterns = _compute_top_patterns(client)
    segments = _segment_cards(client, total_customers=int(kpis.customers.value))
    products = _load_local_data()[0]
    recent = _recent_orders(client, products)
    insight = _build_insight(patterns)

    resp = DashboardResponse(
        kpis=kpis,
        top_patterns=patterns,
        segments=segments,
        insight=insight,
        recent_orders=recent,
        last_query={"endpoint": "_search", "body": kpi_query},
        last_response_ms=kpi_ms,
    )

    cache.set("dashboard:summary", resp.to_dict(), ttl=600)
    return resp


# ── Cache round-trip helper ────────────────────────────────────────


def _from_dict(d: dict) -> DashboardResponse:
    k = d["kpis"]
    return DashboardResponse(
        kpis=Kpis(
            products=Kpi(**k["products"]),
            orders_12mo=Kpi(**k["orders_12mo"]),
            customers=Kpi(**k["customers"]),
            avg_basket_eur=Kpi(**k["avg_basket_eur"]),
        ),
        top_patterns=[Pattern(**p) for p in d["top_patterns"]],
        segments=[SegmentCard(**s) for s in d["segments"]],
        insight=Insight(**d["insight"]),
        recent_orders=[RecentOrder(**o) for o in d["recent_orders"]],
        last_query=d["last_query"],
        last_response_ms=d["last_response_ms"],
    )
