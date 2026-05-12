"""Product Filling — multi-field `_predict` over `products.name`.

Five parallel `_predict` calls (pet_type, category, weight_kg,
dietary, tax_class) keyed on `where = {name, brand}`. The view
hides `pet_type` and `category` even when they're populated in
the DB so the on-screen experience is "five fields filled at
once" per ADR 0009 §"Which fields the demo shows".
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any

from src.aito_client import AitoClient
from src import cache
from src.why_processor import process_why


DATA_DIR = Path(__file__).resolve().parent.parent / "data"


# ── Fields the demo predicts, in display order ────────────────────


PREDICT_FIELDS: list[tuple[str, str]] = [
    ("pet_type",  "Pet type"),
    ("category",  "Category"),
    ("weight_kg", "Weight (kg)"),
    ("dietary",   "Dietary"),
    ("tax_class", "Tax class"),
]

# Two of those (`pet_type`, `category`) are always populated in
# the DB; we render them with a "🔒 stored" tag in the input card
# so the user can see we aren't claiming they were null. Aito
# still predicts them — and gets them right, every time — to
# fill the "five fields" visual.
_ALWAYS_STORED: set[str] = {"pet_type", "category"}


# ── DTOs ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Alternative:
    value: str
    confidence: float


@dataclass(frozen=True)
class WhyFactor:
    field: str
    value: str
    lift: float


@dataclass(frozen=True)
class FillingField:
    field: str
    label: str
    predicted_value: Any
    confidence: float
    alternatives: list[Alternative]
    why_factors: list[WhyFactor]
    why_explanation: dict | None
    hidden_for_demo: bool


@dataclass
class FillingResponse:
    product: dict
    fields: list[FillingField]
    candidate_skus: list[dict]
    last_query: dict
    last_response_ms: int

    def to_dict(self) -> dict:
        return {
            "product":          self.product,
            "fields": [{
                "field":            f.field,
                "label":            f.label,
                "predicted_value":  f.predicted_value,
                "confidence":       f.confidence,
                "alternatives":     [asdict(a) for a in f.alternatives],
                "why_factors":      [asdict(w) for w in f.why_factors],
                "why_explanation":  f.why_explanation,
                "hidden_for_demo":  f.hidden_for_demo,
            } for f in self.fields],
            "candidate_skus":   self.candidate_skus,
            "last_query":       self.last_query,
            "last_response_ms": self.last_response_ms,
        }


# ── Local catalog ─────────────────────────────────────────────────


def _load_products() -> list[dict]:
    return json.loads((DATA_DIR / "products.json").read_text())


def _fillable_products(products: list[dict]) -> list[dict]:
    """Products whose Filling card actually moves data — at least
    one of `weight_kg / dietary / tax_class` is null in the DB."""
    return [
        p for p in products
        if p.get("category") in {"dry-food", "wet-food", "treats", "dental-treats", "litter"}
        and any(p.get(f) is None for f in ("weight_kg", "dietary", "tax_class"))
    ]


# A hand-picked default: this product's name has rich tokens
# ("Sensitive", "Turkey", "Dog", "2kg") so every one of the 5
# predictions lands at p ≥ 0.87 live. Falls back to the first
# fillable product if this SKU is missing for some reason (e.g.
# a fixture regen with a different RNG seed).
_DEFAULT_SKU = "SKU-PT-0038"


# ── Live calls ────────────────────────────────────────────────────


def _parse_why(raw_why: Any) -> list[WhyFactor]:
    """Pull a flat factor list out of Aito's nested `$why`.

    `$why` returns a tree of `$mul` / `$prob` nodes. For the
    demo's WhyTooltip we just need the leaf factors that contribute
    a `lift` and a human-readable `value`. Walk the tree, collect
    the top 4 by absolute deviation from 1.0.
    """
    if not isinstance(raw_why, dict):
        return []
    out: list[WhyFactor] = []

    def walk(node: Any) -> None:
        if not isinstance(node, dict):
            return
        # Leaf: a `$value` with a feature/proposition + lift
        if "lift" in node and "value" in node:
            value = node.get("value")
            prop = value
            if isinstance(value, dict):
                # `value` may be `{"<field>": {"$has": <token>}}` etc.
                inner = next(iter(value.values()), None)
                if isinstance(inner, dict):
                    prop = inner.get("$has") or inner.get("$is") or str(inner)
                else:
                    prop = inner
            field_name = ""
            if isinstance(value, dict):
                field_name = next(iter(value.keys()), "")
            out.append(WhyFactor(
                field=field_name,
                value=str(prop) if prop is not None else "",
                lift=float(node.get("lift", 0)),
            ))
            return
        for v in node.values():
            if isinstance(v, dict):
                walk(v)
            elif isinstance(v, list):
                for item in v:
                    walk(item)

    walk(raw_why)
    out.sort(key=lambda f: abs(f.lift - 1.0), reverse=True)
    return out[:4]


def _predict_field(
    client: AitoClient,
    where: dict,
    predict_field: str,
    label: str,
    hidden_for_demo: bool,
) -> FillingField:
    res = client.predict("products", where=where, predict_field=predict_field, limit=5)
    hits = res.get("hits", [])
    if not hits:
        return FillingField(
            field=predict_field,
            label=label,
            predicted_value=None,
            confidence=0.0,
            alternatives=[],
            why_factors=[],
            why_explanation=None,
            hidden_for_demo=hidden_for_demo,
        )
    top = hits[0]
    predicted_value = top.get("feature")
    confidence = float(top.get("$p", 0))
    alternatives = [
        Alternative(value=str(h.get("feature", "")), confidence=float(h.get("$p", 0)))
        for h in hits[1:4]
    ]
    why_factors = _parse_why(top.get("$why"))
    why_explanation = process_why(top.get("$why"), predicted_value, actual_p=confidence)
    return FillingField(
        field=predict_field,
        label=label,
        predicted_value=predicted_value,
        confidence=confidence,
        alternatives=alternatives,
        why_factors=why_factors,
        why_explanation=why_explanation,
        hidden_for_demo=hidden_for_demo,
    )


# ── Public entry point ────────────────────────────────────────────


def get_filling(
    client: AitoClient,
    *,
    sku: str | None = None,
) -> FillingResponse:
    cache_key = f"filling:{sku or _DEFAULT_SKU}"
    cached = cache.get(cache_key)
    if cached:
        return _from_dict(cached)

    products = _load_products()
    by_sku = {p["sku"]: p for p in products}
    product = by_sku.get(sku) if sku else None
    if product is None:
        product = by_sku.get(_DEFAULT_SKU) or _fillable_products(products)[0]

    where = {"name": product["name"], "brand": product.get("brand", "")}

    body = {
        "from": "products",
        "where": where,
        "predict": "<varies per field>",
        "select": ["$p", "feature", {"$why": {}}],
        "limit": 5,
    }

    started = time.perf_counter()
    # 5 parallel _predict calls — the wall-clock is dominated by
    # the slowest. Cap at 5 workers to match the field count.
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = [
            pool.submit(
                _predict_field,
                client,
                where,
                pf,
                label,
                pf in _ALWAYS_STORED,
            )
            for pf, label in PREDICT_FIELDS
        ]
        fields = [f.result() for f in futures]
    elapsed = int((time.perf_counter() - started) * 1000)

    candidate_skus = [
        {"sku": p["sku"], "name": p["name"]}
        for p in _fillable_products(products)
    ][:30]

    resp = FillingResponse(
        product={
            "sku":        product["sku"],
            "name":       product["name"],
            "brand":      product.get("brand", ""),
            "pet_type":   product.get("pet_type", ""),
            "category":   product.get("category", ""),
            "weight_kg":  product.get("weight_kg"),
            "dietary":    product.get("dietary"),
            "tax_class":  product.get("tax_class"),
            "price_eur":  round(float(product.get("price_eur", 0)), 2),
        },
        fields=fields,
        candidate_skus=candidate_skus,
        last_query={"endpoint": "_predict", "body": body},
        last_response_ms=elapsed,
    )

    cache.set(cache_key, resp.to_dict(), ttl=1800)
    return resp


# ── Cache round-trip ──────────────────────────────────────────────


def _from_dict(d: dict) -> FillingResponse:
    return FillingResponse(
        product=d["product"],
        fields=[
            FillingField(
                field=f["field"],
                label=f["label"],
                predicted_value=f["predicted_value"],
                confidence=f["confidence"],
                alternatives=[Alternative(**a) for a in f["alternatives"]],
                why_factors=[WhyFactor(**w) for w in f["why_factors"]],
                why_explanation=f.get("why_explanation"),
                hidden_for_demo=f["hidden_for_demo"],
            )
            for f in d["fields"]
        ],
        candidate_skus=d["candidate_skus"],
        last_query=d["last_query"],
        last_response_ms=d["last_response_ms"],
    )
