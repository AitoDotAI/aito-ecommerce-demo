"""Win-back campaigns — for each currently-churned customer,
predict which products they'll respond to in an email, and the
revenue impact if they do.

Mirrors the Netigate accounting-demo "action + impact estimation"
pattern: historical outcomes (`winback_campaigns.responded`) let
Aito's `_predict` empirically estimate the response rate for the
current customer × candidate product. Multiply by predicted
order-value and you have €recoverable revenue per send.

Three live calls per customer (parallel):
  1. `_recommend product_sku from winback_campaigns
       where {customer_lifestyle, customer_segment, recency_bucket}
       goal {responded: true}`
     → top-3 products by predicted attach probability.
  2. `_predict responded` for each suggested product — to read the
     calibrated response probability (`_recommend` returns it but
     normalised against goal-positives, not absolute).
  3. `_predict order_value_eur` for each suggested product — gives
     the basket-value forecast that turns response rate into €.

Cached 30 minutes. Top-20 churned customers by `total_spent_eur`
— the segment where re-engagement spend pays off most.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict
from typing import Any

from src.aito_client import AitoClient
from src import cache


DEMO_TODAY_YYYYMM = "2026-04"
TOP_N_CUSTOMERS = 20

# Average per-email send cost, used to net out from the gross
# revenue estimate. €0.50 is a representative figure for an
# automated SendGrid / Mailchimp re-engagement programme.
EMAIL_COST_EUR = 0.50


# ── DTOs ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ProductSuggestion:
    sku: str
    name: str
    pet_type: str
    category: str
    brand: str
    price_eur: float
    response_p: float        # P(responded | this product, this customer's context)
    predicted_aov_eur: float # predicted order_value_eur if they respond
    expected_revenue_eur: float  # response_p × aov − cost
    rank: int


@dataclass(frozen=True)
class WinbackTarget:
    customer_id: str
    customer_name: str
    segment: str
    pet_size: str | None
    lifestyle: str
    health_focus: str
    recency_bucket: str       # derived from last_order_month vs DEMO_TODAY
    last_order_month: str
    total_spent_eur: float
    total_orders: int
    suggestions: list[ProductSuggestion]
    expected_recovered_eur: float  # sum of suggestion expected_revenue_eur


@dataclass(frozen=True)
class Kpi:
    label: str
    value: float
    sub: str


@dataclass
class WinbackResponse:
    kpis: list[Kpi]
    targets: list[WinbackTarget]
    last_query: dict
    last_response_ms: int

    def to_dict(self) -> dict:
        return {
            "kpis":             [asdict(k) for k in self.kpis],
            "targets":          [_target_to_dict(t) for t in self.targets],
            "last_query":       self.last_query,
            "last_response_ms": self.last_response_ms,
        }


def _target_to_dict(t: WinbackTarget) -> dict:
    d = asdict(t)
    # suggestions is already dict-ified by asdict
    return d


# ── Helpers ───────────────────────────────────────────────────────


def _months_diff(yyyymm_a: str, yyyymm_b: str) -> int:
    """Approximate days difference in months between two YYYY-MM
    strings — used to convert last_order_month to a recency bucket."""
    ya, ma = int(yyyymm_a[:4]), int(yyyymm_a[5:])
    yb, mb = int(yyyymm_b[:4]), int(yyyymm_b[5:])
    return (yb - ya) * 12 + (mb - ma)


def _recency_bucket_from_last_order(last_order_month: str) -> str:
    """Map last_order_month → the same bucket the campaigns fixture uses."""
    months = _months_diff(last_order_month, DEMO_TODAY_YYYYMM)
    if months <= 3:
        return "0-90d"
    if months <= 6:
        return "90-180d"
    return "180d+"


# ── Live calls ─────────────────────────────────────────────────────


def _fetch_churned_customers(client: AitoClient) -> list[dict]:
    """Top-N churned customers by total_spent_eur. These are the
    win-back priority — most revenue per re-engagement send."""
    res = client.search(
        "customers",
        where={"churned": True},
        limit=TOP_N_CUSTOMERS * 3,   # over-fetch, then sort + trim
        offset=0,
    )
    hits = res.get("hits", [])
    hits.sort(key=lambda c: -float(c.get("total_spent_eur", 0) or 0))
    return hits[:TOP_N_CUSTOMERS]


def _recommend_products(
    client: AitoClient,
    customer: dict,
    recency_bucket: str,
) -> list[dict]:
    """Top-3 product recommendations for one churned customer.

    `_recommend product_sku from winback_campaigns` conditions on
    the customer's profile + recency bucket, ranking candidates
    by `P(responded=true | this product, this customer)`.
    """
    where: dict[str, Any] = {
        "customer_lifestyle":   customer["lifestyle"],
        "customer_segment":     customer["segment"],
        "customer_health_focus":customer["health_focus"],
        "recency_bucket":       recency_bucket,
    }
    if customer.get("pet_size"):
        where["customer_pet_size"] = customer["pet_size"]

    res = client.recommend(
        table="winback_campaigns",
        where=where,
        recommend_field="product_sku",
        goal={"responded": True},
        based_on=["pet_type", "category", "brand"],   # relative to the recommend target (products)
        limit=8,   # over-fetch in case of duplicates / weak hits
    )
    return res.get("hits", [])


def _predict_aov_for_product(
    client: AitoClient,
    customer: dict,
    product_sku: str,
    recency_bucket: str,
) -> float:
    """Predict the order_value_eur for a customer × product pair,
    conditioned on profile + recency. `_estimate` because order
    value is continuous."""
    where: dict[str, Any] = {
        "customer_lifestyle":   customer["lifestyle"],
        "customer_segment":     customer["segment"],
        "recency_bucket":       recency_bucket,
        "product_sku":          product_sku,
        # Goal-side: we want the conditional expectation given
        # responded=true, since order_value is 0 otherwise.
        "responded":            True,
    }
    if customer.get("pet_size"):
        where["customer_pet_size"] = customer["pet_size"]
    try:
        res = client.estimate(
            "winback_campaigns",
            where=where,
            estimate_field="order_value_eur",
            with_why=False,
        )
        v = res.get("estimate")
        return max(0.0, float(v)) if v is not None else 0.0
    except Exception:
        return 0.0


def _score_customer(
    client: AitoClient,
    customer: dict,
) -> WinbackTarget | None:
    """Build one customer's win-back recommendation block."""
    last_order = customer.get("last_order_month") or DEMO_TODAY_YYYYMM
    recency = _recency_bucket_from_last_order(last_order)

    recs = _recommend_products(client, customer, recency)
    if not recs:
        return None

    # Build suggestions. For each top hit, the recommend hit carries
    # both the product fields (linked-table flattening) AND $p
    # (Aito's calibrated probability of responded=true).
    suggestions: list[ProductSuggestion] = []
    seen: set[str] = set()
    for h in recs:
        if len(suggestions) >= 3:
            break
        sku = h.get("sku") or h.get("feature") or ""
        if not sku or sku in seen:
            continue
        seen.add(sku)
        response_p = float(h.get("$p", 0) or 0)
        price = float(h.get("price_eur", 0) or 0)
        # AOV: use the per-product estimate when it works, else
        # fall back to 2× the product's price (typical basket
        # multiplier for re-engaged customers).
        aov = _predict_aov_for_product(client, customer, sku, recency)
        if aov <= 0:
            aov = round(price * 2.0, 2)
        expected = round(response_p * aov - EMAIL_COST_EUR, 2)
        suggestions.append(ProductSuggestion(
            sku=sku,
            name=h.get("name", sku),
            pet_type=h.get("pet_type", ""),
            category=h.get("category", ""),
            brand=h.get("brand", ""),
            price_eur=round(price, 2),
            response_p=round(response_p, 3),
            predicted_aov_eur=round(aov, 2),
            expected_revenue_eur=expected,
            rank=len(suggestions) + 1,
        ))

    expected_total = round(sum(s.expected_revenue_eur for s in suggestions), 2)

    return WinbackTarget(
        customer_id=customer["customer_id"],
        customer_name=customer.get("name", customer["customer_id"]),
        segment=customer["segment"],
        pet_size=customer.get("pet_size"),
        lifestyle=customer["lifestyle"],
        health_focus=customer["health_focus"],
        recency_bucket=recency,
        last_order_month=last_order,
        total_spent_eur=round(float(customer.get("total_spent_eur", 0) or 0), 2),
        total_orders=int(customer.get("total_orders", 0) or 0),
        suggestions=suggestions,
        expected_recovered_eur=expected_total,
    )


# ── Public entry point ─────────────────────────────────────────────


def get_winback(client: AitoClient) -> WinbackResponse:
    cached = cache.get("winback:summary")
    if cached:
        return _from_dict(cached)

    started = time.perf_counter()

    customers = _fetch_churned_customers(client)
    if not customers:
        return WinbackResponse(
            kpis=[], targets=[],
            last_query={"endpoint": "_recommend", "body": {}},
            last_response_ms=int((time.perf_counter() - started) * 1000),
        )

    # Score customers in parallel. Each `_score_customer` runs one
    # `_recommend` + up to 3 `_estimate` calls = 4 calls per
    # customer. 20 customers × 4 calls = 80 total; pool of 4
    # parallel customer-workers keeps in-flight under Aito's
    # ceiling.
    with ThreadPoolExecutor(max_workers=4) as pool:
        targets = [t for t in pool.map(lambda c: _score_customer(client, c), customers)
                   if t is not None]

    targets.sort(key=lambda t: -t.expected_recovered_eur)

    total_recovered = round(sum(t.expected_recovered_eur for t in targets), 2)
    total_sends = sum(len(t.suggestions) for t in targets)
    avg_response_p = round(
        sum(s.response_p for t in targets for s in t.suggestions)
        / max(1, total_sends),
        3,
    )

    kpis = [
        Kpi("Targets identified", float(len(targets)),
            "churned customers worth re-engaging"),
        Kpi("Predicted recoverable revenue", total_recovered,
            f"sum of response_p × AOV − €{EMAIL_COST_EUR:.2f}/email across {total_sends} sends"),
        Kpi("Average response rate", avg_response_p,
            "across all proposed (customer × product) sends"),
        Kpi("Campaign cost", round(total_sends * EMAIL_COST_EUR, 2),
            f"€{EMAIL_COST_EUR:.2f} × {total_sends} emails"),
    ]

    sample_body = {
        "from":      "winback_campaigns",
        "where":     {
            "customer_lifestyle":   "premium",
            "customer_segment":     "dog_owner",
            "recency_bucket":       "0-90d",
        },
        "recommend": "product_sku",
        "goal":      {"responded": True},
        "basedOn":   ["pet_type", "category", "brand"],
        "limit":     8,
    }

    elapsed = int((time.perf_counter() - started) * 1000)
    resp = WinbackResponse(
        kpis=kpis,
        targets=targets,
        last_query={"endpoint": "_recommend", "body": sample_body},
        last_response_ms=elapsed,
    )
    cache.set("winback:summary", resp.to_dict(), ttl=1800)
    return resp


def _from_dict(d: dict) -> WinbackResponse:
    return WinbackResponse(
        kpis=[Kpi(**k) for k in d["kpis"]],
        targets=[
            WinbackTarget(
                **{k: v for k, v in t.items() if k != "suggestions"},
                suggestions=[ProductSuggestion(**s) for s in t["suggestions"]],
            )
            for t in d["targets"]
        ],
        last_query=d["last_query"],
        last_response_ms=d["last_response_ms"],
    )
