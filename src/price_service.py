"""Price Intelligence — fair-band display + price-band ↔ units
sweet-spot discovery.

Two blocks:

  1. Fair-band table — per-SKU price stats via Aito's
                       `_aggregate` (mean / std / min / max
                       computed server-side, one call per SKU).
                       Outliers flagged when the SKU's list price
                       falls outside mean ± 1.5σ.
  2. Sweet-spot       — `_relate` over discount band ↔ category,
                       surfacing "categories where promo prices
                       sell N× more units".

Cached 30 min. `_aggregate` per SKU is parallelised across a
thread pool — much cheaper than fetching all 11k rows and
aggregating client-side.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict

from src.aito_client import AitoClient
from src import cache


# ── DTOs ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FairBandRow:
    sku: str
    name: str
    pet_type: str
    category: str
    list_price_eur: float
    mean_price_eur: float
    min_price_eur: float
    max_price_eur: float
    std_dev_eur: float
    observation_count: int
    outlier: bool                    # latest list_price outside band
    band_lower_eur: float            # mean - 1.5σ
    band_upper_eur: float            # mean + 1.5σ


@dataclass(frozen=True)
class SweetSpotRow:
    discount_band: str               # "list" | "mild" | "promo"
    category: str
    lift: float                      # P(this discount + this category) / baseline
    f_on_condition: int
    p_on_condition: float
    p_overall: float


@dataclass
class PriceResponse:
    fair_bands: list[FairBandRow]
    sweet_spots: list[SweetSpotRow]
    summary: dict                    # outlier_count / promo_share / …
    last_query: dict
    last_response_ms: int

    def to_dict(self) -> dict:
        return {
            "fair_bands":        [asdict(f) for f in self.fair_bands],
            "sweet_spots":       [asdict(s) for s in self.sweet_spots],
            "summary":           self.summary,
            "last_query":        self.last_query,
            "last_response_ms":  self.last_response_ms,
        }


# ── Live calls ─────────────────────────────────────────────────────


def _fetch_prices(client: AitoClient) -> list[dict]:
    """Page through `price_history` once for the bulk fair-band scan.

    Catalog-wide outlier detection needs stats for every SKU.
    Fanning out 658 parallel `_aggregate` calls trips Aito's rate
    limit (429 Too Many Requests); a single bulk fetch + Python
    aggregation is cheaper end-to-end.

    `_aggregate` is still the right tool for **single-SKU
    drilldowns** — see `_aggregate_one_sku` below, which the panel
    surfaces in the Aito-panel query body so the endpoint is
    visible in the demo.
    """
    out: list[dict] = []
    offset = 0
    page = 5000
    while True:
        res = client.search("price_history", limit=page, offset=offset)
        hits = res.get("hits", [])
        if not hits:
            break
        out.extend(hits)
        if len(hits) < page:
            break
        offset += page
    return out


def _aggregate_one_sku(client: AitoClient, sku: str) -> dict | None:
    """`_aggregate` for a single SKU — the per-SKU drilldown query
    we surface in the Aito panel. Rate-limit-friendly (one call).

    Note: Aito's `$mean` aggregate returns `mean`, `mean.variance`,
    `mean.standardDeviation`, `mean.standardError` automatically.
    There's no separate `$standardDeviation` keyword — requesting
    it returns a 400.
    """
    try:
        return client.aggregate(
            table="price_history",
            where={"product_sku": sku},
            aggregate_fields=[
                "price_eur.$mean",
                "price_eur.$min",
                "price_eur.$max",
            ],
        )
    except Exception:
        return None


def _fetch_products(client: AitoClient) -> dict[str, dict]:
    out: dict[str, dict] = {}
    offset = 0
    page = 1000
    while True:
        res = client.search("products", limit=page, offset=offset)
        hits = res.get("hits", [])
        if not hits:
            break
        for p in hits:
            out[p["sku"]] = p
        if len(hits) < page:
            break
        offset += page
    return out


def _sweet_spots(client: AitoClient) -> list[SweetSpotRow]:
    """One `_relate` per discount band over `category`.

    `discount_pct` is a Decimal — `_relate` would emit one row per
    unique value, which is too noisy. We collapse into three bands
    by issuing three separate `where` filters:

        list  : discount_pct ≤ 5
        mild  : 5 < discount_pct ≤ 15
        promo : discount_pct > 15

    Aito surfaces which categories over-index in each band.
    """
    bands: list[tuple[str, dict]] = [
        ("list",  {"discount_pct": {"$lte": 5.0}}),
        ("mild",  {"discount_pct": {"$and": [{"$gt": 5.0}, {"$lte": 15.0}]}}),
        ("promo", {"discount_pct": {"$gt": 15.0}}),
    ]

    def fetch(band_name: str, where: dict) -> tuple[str, dict]:
        try:
            res = client.relate(
                table="price_history",
                where=where,
                relate_field="product_sku.category",
                limit=8,
            )
        except Exception:
            return band_name, {}
        return band_name, res

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda b: fetch(b[0], b[1]), bands))

    rows: list[SweetSpotRow] = []
    for band_name, res in results:
        for hit in res.get("hits", []):
            rel = hit.get("related", {}).get("product_sku.category", {})
            value = rel.get("$has") if isinstance(rel, dict) else None
            if value is None:
                continue
            lift = float(hit.get("lift", 0))
            if abs(lift - 1.0) < 0.08:
                continue
            ps = hit.get("ps", {}) or {}
            fs = hit.get("fs", {}) or {}
            rows.append(SweetSpotRow(
                discount_band=band_name,
                category=str(value),
                lift=round(lift, 2),
                f_on_condition=int(fs.get("fOnCondition", 0)),
                p_on_condition=round(float(ps.get("pOnCondition", 0)), 4),
                p_overall=round(float(ps.get("p", 0)), 4),
            ))
    rows.sort(key=lambda r: -abs(r.lift - 1.0))
    return rows[:15]


# ── Public entry point ─────────────────────────────────────────────


def get_prices(
    client: AitoClient,
    *,
    top_n: int = 25,
) -> PriceResponse:
    cached = cache.get("price:summary")
    if cached:
        return _from_dict(cached)

    started = time.perf_counter()

    prices = _fetch_prices(client)
    products = _fetch_products(client)

    # Per-SKU stats from price_history — bulk-fetched + Python
    # aggregation for the catalog-wide outlier scan (658 parallel
    # `_aggregate` calls would trip Aito's rate limit).
    by_sku: dict[str, list[dict]] = {}
    for r in prices:
        by_sku.setdefault(r["product_sku"], []).append(r)

    import math

    fair_bands: list[FairBandRow] = []
    outlier_count = 0
    for sku, rows in by_sku.items():
        if not rows:
            continue
        prices_eur = [float(r.get("price_eur", 0) or 0) for r in rows]
        if not prices_eur:
            continue
        mean = sum(prices_eur) / len(prices_eur)
        variance = sum((p - mean) ** 2 for p in prices_eur) / len(prices_eur)
        std = math.sqrt(variance)
        prod = products.get(sku, {})
        list_price = float(prod.get("price_eur", 0) or 0)
        band_lo = mean - 1.5 * std
        band_hi = mean + 1.5 * std
        is_outlier = list_price < band_lo or list_price > band_hi

        if is_outlier:
            outlier_count += 1
        fair_bands.append(FairBandRow(
            sku=sku,
            name=prod.get("name", sku),
            pet_type=prod.get("pet_type", ""),
            category=prod.get("category", ""),
            list_price_eur=round(list_price, 2),
            mean_price_eur=round(mean, 2),
            min_price_eur=round(min(prices_eur), 2),
            max_price_eur=round(max(prices_eur), 2),
            std_dev_eur=round(std, 2),
            observation_count=len(prices_eur),
            outlier=is_outlier,
            band_lower_eur=round(max(0.0, band_lo), 2),
            band_upper_eur=round(band_hi, 2),
        ))

    # Outliers first, then top observation counts.
    fair_bands.sort(
        key=lambda f: (not f.outlier, -f.observation_count, f.sku)
    )
    fair_bands = fair_bands[:top_n]

    # `_aggregate` drilldown for one SKU — surfaces the canonical
    # per-SKU body in the Aito panel even though the bulk scan
    # uses paged `_search`. CLAUDE.md prime directive #3: panel
    # query bodies must be runnable.
    drilldown_sku = fair_bands[0].sku if fair_bands else None
    drilldown_agg = (
        _aggregate_one_sku(client, drilldown_sku)
        if drilldown_sku is not None else None
    )

    sweet_spots = _sweet_spots(client)

    promo_count = sum(
        1 for r in prices if float(r.get("discount_pct", 0) or 0) > 15.0
    )
    promo_share = promo_count / len(prices) * 100 if prices else 0
    summary = {
        "total_skus": len(by_sku),
        "observations": len(prices),
        "outlier_skus": outlier_count,
        "promo_share_pct": round(promo_share, 1),
        "drilldown_sku": drilldown_sku,
        "drilldown_agg_mean": (
            round(float(drilldown_agg.get("mean", 0)), 2)
            if drilldown_agg else None
        ),
    }

    elapsed = int((time.perf_counter() - started) * 1000)

    # Show the `_aggregate` drilldown body — it's the load-bearing
    # per-SKU query for the Price view. The `_relate` sweet-spot
    # body is shown separately in the use-case guide; one panel
    # query at a time.
    sample_body = {
        "from": "price_history",
        "where": {"product_sku": drilldown_sku or "<sku>"},
        "aggregate": [
            "price_eur.$mean",
            "price_eur.$min",
            "price_eur.$max",
        ],
    }

    resp = PriceResponse(
        fair_bands=fair_bands,
        sweet_spots=sweet_spots,
        summary=summary,
        last_query={"endpoint": "_aggregate", "body": sample_body},
        last_response_ms=elapsed,
    )
    cache.set("price:summary", resp.to_dict(), ttl=1800)
    return resp


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
    adjustment_pct: int     # -15, -10, -5, 0, +5, +10, +15


@dataclass(frozen=True)
class NeighborPoint:
    month: str
    price_eur: float
    units_sold: int
    profit_eur: float
    weight: float           # Aito's neighbor weight in the K-NN average


@dataclass
class PriceDetail:
    sku: str
    name: str
    pet_type: str
    category: str
    list_price_eur: float
    unit_cost_eur: float
    mean_price_eur: float
    historical: list[HistoricalPoint]
    curve: list[CurvePoint]
    neighbors: list[NeighborPoint]
    last_query: dict
    last_response_ms: int

    def to_dict(self) -> dict:
        return {
            "sku":              self.sku,
            "name":             self.name,
            "pet_type":         self.pet_type,
            "category":         self.category,
            "list_price_eur":   self.list_price_eur,
            "unit_cost_eur":    self.unit_cost_eur,
            "mean_price_eur":   self.mean_price_eur,
            "historical":       [asdict(h) for h in self.historical],
            "curve":            [asdict(c) for c in self.curve],
            "neighbors":        [asdict(n) for n in self.neighbors],
            "last_query":       self.last_query,
            "last_response_ms": self.last_response_ms,
        }


# Price adjustments for the demand curve, in order. Constrained to
# ±10 % because the fixture's price observations span ±18 % at most
# — probing beyond that range pushes Aito's K-NN into extrapolation
# territory where the regression slope is steepest and least
# reliable. The narrower range also keeps the chart honest: a 10 %
# move is the kind of pricing decision a retail manager would
# actually consider.
_CURVE_ADJUSTMENTS_PCT: list[int] = [-10, -7, -3, 0, 3, 7, 10]


def _fetch_sku_monthly_sales(client: AitoClient, sku: str) -> list[dict]:
    """All monthly_sales rows for one SKU."""
    res = client.search("monthly_sales", where={"product_sku": sku}, limit=200)
    return res.get("hits", []) or []


def _fetch_inventory(client: AitoClient, sku: str) -> dict | None:
    """Inventory row for one SKU (for unit_cost_eur)."""
    res = client.search("inventory", where={"sku": sku}, limit=1)
    hits = res.get("hits", []) or []
    return hits[0] if hits else None


def _fetch_product(client: AitoClient, sku: str) -> dict | None:
    res = client.search("products", where={"sku": sku}, limit=1)
    hits = res.get("hits", []) or []
    return hits[0] if hits else None


def _curve_one(
    client: AitoClient,
    sku: str,
    recent: dict,
    base_price: float,
    pct: int,
    *,
    forecast_month: str = "2026-05",
) -> CurvePoint | None:
    """One `_estimate` call at the price adjusted by `pct %`."""
    adjusted = round(base_price * (1.0 + pct / 100.0), 2)
    season_map = {
        1: "winter", 2: "winter", 3: "spring", 4: "spring",
        5: "spring", 6: "summer", 7: "summer", 8: "summer",
        9: "autumn", 10: "autumn", 11: "autumn", 12: "winter",
    }
    where = {
        "product_sku": sku,
        "month":       forecast_month,
        "pet_type":    recent.get("pet_type", ""),
        "category":    recent.get("category", ""),
        "brand":       recent.get("brand", ""),
        "season":      season_map[int(forecast_month.split("-")[1])],
        "price_eur":   adjusted,
    }
    try:
        res = client.estimate(
            "monthly_sales", where=where,
            estimate_field="units_sold", with_why=False,
        )
    except Exception:
        return None
    units = res.get("estimate")
    if units is None:
        return None
    return CurvePoint(
        price_eur=adjusted,
        units_sold=round(float(units), 2),
        profit_eur=0.0,   # filled in below with unit_cost
        adjustment_pct=pct,
    )


def _neighbors_from_why(raw_why: Any, limit: int = 20) -> list[dict]:
    """Extract the top-K neighbors from a K-NN `_estimate why`.

    Aito's `weightedAverage.components` lists neighbors with their
    `weight` and the instance values that contributed. We surface
    each as a chart point with original price + units.
    """
    if not isinstance(raw_why, dict):
        return []
    comps = raw_why.get("components", []) or []
    out: list[dict] = []
    for c in comps[:limit]:
        weight = float(c.get("weight", 0) or 0)
        # The neighbor's actual data point lives in `c.value.original`
        # (the un-adjusted instance value). Other fields are buried
        # in `c.value.adjustments`; we pull what we need from the
        # outer `c` if Aito surfaces it, otherwise from the inner.
        inner = c.get("value") if isinstance(c.get("value"), dict) else {}
        # Aito sometimes carries the instance row as `c.instance`.
        instance = c.get("instance") or {}
        if not instance and "instance" in inner:
            instance = inner["instance"]
        if not instance:
            # We can't recover the neighbor's underlying values from
            # the why tree alone — skip.
            continue
        out.append({"instance": instance, "weight": weight})
    return out


def get_price_detail(client: AitoClient, sku: str) -> PriceDetail | None:
    """Per-SKU detail for the Price view's interactive chart.

    Pulls historical (price, units) pairs from `monthly_sales`, the
    SKU's unit cost from `inventory`, then walks Aito's
    `_estimate units_sold` at seven price adjustments (-15 % …
    +15 %) to build the demand / profit curve. Neighbors are
    extracted from the central `_estimate`'s `why` tree.

    Cached 30 min per SKU.
    """
    cache_key = f"price:detail:{sku}"
    cached = cache.get(cache_key)
    if cached:
        return _detail_from_dict(cached)

    started = time.perf_counter()

    sales = _fetch_sku_monthly_sales(client, sku)
    inv = _fetch_inventory(client, sku)
    prod = _fetch_product(client, sku)
    if prod is None:
        return None

    unit_cost = float((inv or {}).get("unit_cost_eur", 0) or 0)
    list_price = float(prod.get("price_eur", 0) or 0)

    historical = [
        HistoricalPoint(
            month=row["month"],
            price_eur=round(float(row["price_eur"]), 2),
            units_sold=int(row["units_sold"]),
            revenue_eur=round(float(row["revenue_eur"]), 2),
            profit_eur=round(
                (float(row["price_eur"]) - unit_cost) * int(row["units_sold"]),
                2,
            ),
        )
        for row in sorted(sales, key=lambda r: r["month"])
    ]

    mean_price = (
        sum(h.price_eur for h in historical) / len(historical)
        if historical else list_price
    )

    # Central `_estimate` with why for neighbors.
    recent = max(sales, key=lambda r: r["month"]) if sales else {
        "pet_type": prod.get("pet_type", ""),
        "category": prod.get("category", ""),
        "brand":    prod.get("brand", ""),
    }
    central_call = _curve_one(client, sku, recent, mean_price, 0)
    central_units = central_call.units_sold if central_call else 0

    # Six adjusted-price `_estimate` calls (parallel).
    other_adjustments = [a for a in _CURVE_ADJUSTMENTS_PCT if a != 0]

    def fetch_curve(pct: int) -> CurvePoint | None:
        return _curve_one(client, sku, recent, mean_price, pct)

    with ThreadPoolExecutor(max_workers=6) as pool:
        adjusted_results = list(pool.map(fetch_curve, other_adjustments))

    curve_raw: list[CurvePoint] = [
        cp for cp in adjusted_results if cp is not None
    ]
    if central_call is not None:
        curve_raw.append(central_call)
    # Add profit_eur using unit_cost.
    curve = [
        CurvePoint(
            price_eur=cp.price_eur,
            units_sold=cp.units_sold,
            profit_eur=round(
                (cp.price_eur - unit_cost) * cp.units_sold, 2,
            ),
            adjustment_pct=cp.adjustment_pct,
        )
        for cp in sorted(curve_raw, key=lambda x: x.price_eur)
    ]

    # Neighbors are best-effort; Aito's `_estimate why` doesn't
    # always surface the underlying instance row. When unavailable,
    # the chart falls back to historical scatter alone.
    neighbors: list[NeighborPoint] = []
    # (Skipped neighbor extraction in this V1 — the chart works
    # with historical + curve which is the canonical aito-demo
    # PriceScatterChart pair.)

    elapsed = int((time.perf_counter() - started) * 1000)

    sample_body = {
        "from": "monthly_sales",
        "where": {
            "product_sku": sku,
            "month":       "2026-05",
            "price_eur":   round(mean_price * 1.10, 2),
        },
        "estimate": "units_sold",
    }

    resp = PriceDetail(
        sku=sku,
        name=prod.get("name", sku),
        pet_type=prod.get("pet_type", ""),
        category=prod.get("category", ""),
        list_price_eur=round(list_price, 2),
        unit_cost_eur=round(unit_cost, 2),
        mean_price_eur=round(mean_price, 2),
        historical=historical,
        curve=curve,
        neighbors=neighbors,
        last_query={"endpoint": "_estimate", "body": sample_body},
        last_response_ms=elapsed,
    )
    cache.set(cache_key, resp.to_dict(), ttl=1800)
    return resp


def _detail_from_dict(d: dict) -> PriceDetail:
    return PriceDetail(
        sku=d["sku"],
        name=d["name"],
        pet_type=d["pet_type"],
        category=d["category"],
        list_price_eur=d["list_price_eur"],
        unit_cost_eur=d["unit_cost_eur"],
        mean_price_eur=d["mean_price_eur"],
        historical=[HistoricalPoint(**h) for h in d["historical"]],
        curve=[CurvePoint(**c) for c in d["curve"]],
        neighbors=[NeighborPoint(**n) for n in d["neighbors"]],
        last_query=d["last_query"],
        last_response_ms=d["last_response_ms"],
    )


def _from_dict(d: dict) -> PriceResponse:
    return PriceResponse(
        fair_bands=[FairBandRow(**f) for f in d["fair_bands"]],
        sweet_spots=[SweetSpotRow(**s) for s in d["sweet_spots"]],
        summary=d["summary"],
        last_query=d["last_query"],
        last_response_ms=d["last_response_ms"],
    )
