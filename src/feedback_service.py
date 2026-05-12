"""Feedback — multi-field `_predict` over review text.

A support-queue triage view: incoming review text in, three predicted
fields out (category, sentiment, assigned_to) in one round-trip via
three parallel `_predict` calls.

Same fanout shape as Product Filling (`src/filling_service.py`),
applied to free-form text instead of structured product attributes.
The Aito panel shows the underlying query body — three single-field
predicts with the same `where: {text: <review text>}` conditioning.

See ADR 0012 for the design rationale and the multi-class
classification trade-offs.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from src.aito_client import AitoClient
from src import cache
from src.why_processor import process_why


DATA_DIR = Path(__file__).resolve().parent.parent / "data"


# Fields the demo predicts, in display order. Three classifications
# (category / sentiment / assigned_to) plus the forward-looking
# `churn_within_90d` — Aito predicts churn risk straight from the
# review text. See ADR 0012 §"Forward labels" + ADR 0013.
PREDICT_FIELDS: list[tuple[str, str]] = [
    ("category",          "Issue category"),
    ("sentiment",         "Sentiment"),
    ("assigned_to",       "Suggested assignee"),
    ("churn_within_90d",  "Churn risk (90 d)"),
]


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
class PredictedField:
    field: str
    label: str
    predicted_value: Any
    confidence: float
    alternatives: list[Alternative]
    why_factors: list[WhyFactor]
    why_explanation: dict | None


@dataclass(frozen=True)
class ReviewSummary:
    review_id: str
    customer_id: str
    customer_short: str
    product_sku: str
    product_name: str
    rating: int
    text: str
    created_at: str
    # Ground-truth labels from the fixture — surfaced so the UI can
    # render the prediction side by side with what was stored. Aito
    # doesn't see these at predict time.
    actual_category: str
    actual_sentiment: str
    actual_assigned_to: str
    actual_churn_within_90d: bool


@dataclass
class FeedbackResponse:
    review: ReviewSummary
    fields: list[PredictedField]
    candidate_reviews: list[dict]
    last_query: dict
    last_response_ms: int

    def to_dict(self) -> dict:
        return {
            "review":   asdict(self.review),
            "fields": [{
                "field":           f.field,
                "label":           f.label,
                "predicted_value": f.predicted_value,
                "confidence":      f.confidence,
                "alternatives":    [asdict(a) for a in f.alternatives],
                "why_factors":     [asdict(w) for w in f.why_factors],
                "why_explanation": f.why_explanation,
            } for f in self.fields],
            "candidate_reviews": self.candidate_reviews,
            "last_query":        self.last_query,
            "last_response_ms":  self.last_response_ms,
        }


# ── Local catalog ─────────────────────────────────────────────────


def _load_reviews() -> list[dict]:
    return json.loads((DATA_DIR / "reviews.json").read_text())


def _load_products() -> dict[str, dict]:
    return {p["sku"]: p for p in json.loads((DATA_DIR / "products.json").read_text())}


_FIRST_NAMES = [
    "Mikko", "Sari", "Antti", "Maija", "Olli", "Saara", "Liisa", "Janne",
    "Heidi", "Pekka", "Maria", "Joonas", "Erika", "Henrik", "Petra",
]


def _short_customer_name(customer_id: str) -> str:
    h = sum(ord(c) for c in customer_id)
    first = _FIRST_NAMES[h % len(_FIRST_NAMES)]
    initial = chr(ord("A") + ((h // 7) % 26))
    return f"{first} {initial}."


# A hand-picked default review whose text has rich classification
# signal — a "quality" review with the trigger words Aito learns to
# pick up. Falls back to the first review if missing.
_DEFAULT_REVIEW_ID = "REV-00001"


# ── Live calls ────────────────────────────────────────────────────


def _parse_why(raw_why: Any) -> list[WhyFactor]:
    """Pull a flat factor list out of Aito's nested `$why` tree.

    Same logic as Product Filling's `_parse_why` — `$why` returns a
    `$mul` / `$prob` tree; we walk it for leaf factors that carry a
    `lift` and a human-readable value. Top 4 by deviation from 1.0.
    """
    if not isinstance(raw_why, dict):
        return []
    out: list[WhyFactor] = []

    def walk(node: Any) -> None:
        if not isinstance(node, dict):
            return
        if "lift" in node and "value" in node:
            value = node.get("value")
            prop = value
            if isinstance(value, dict):
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
) -> PredictedField:
    res = client.predict("reviews", where=where, predict_field=predict_field, limit=5)
    hits = res.get("hits", [])
    if not hits:
        return PredictedField(
            field=predict_field, label=label,
            predicted_value=None, confidence=0.0,
            alternatives=[], why_factors=[], why_explanation=None,
        )

    # For Boolean risk-style fields we always want to explain the TRUE
    # class — the popover header reads "Why churn risk = 6 %?" and the
    # body's base-P + lifts have to be the factors that produce that
    # 6 % (not the 94 % of P(False)). Without this branch the popover
    # tells two different stories: title says "6 %", body explains
    # "94 %".
    if predict_field == "churn_within_90d":
        top = next(
            (h for h in hits if h.get("feature") is True
             or h.get("feature") == "true"),
            hits[0],
        )
    else:
        top = hits[0]

    predicted_value = top.get("feature")
    confidence = float(top.get("$p", 0))
    alternatives = [
        Alternative(value=str(h.get("feature", "")), confidence=float(h.get("$p", 0)))
        for h in hits[1:4] if h is not top
    ]
    why_factors = _parse_why(top.get("$why"))
    why_explanation = process_why(top.get("$why"), predicted_value, actual_p=confidence)
    return PredictedField(
        field=predict_field, label=label,
        predicted_value=predicted_value,
        confidence=confidence,
        alternatives=alternatives,
        why_factors=why_factors,
        why_explanation=why_explanation,
    )


# ── Public entry point ────────────────────────────────────────────


def get_feedback(
    client: AitoClient,
    *,
    review_id: str | None = None,
) -> FeedbackResponse:
    cache_key = f"feedback:{review_id or _DEFAULT_REVIEW_ID}"
    cached = cache.get(cache_key)
    if cached:
        return _from_dict(cached)

    reviews = _load_reviews()
    products = _load_products()
    by_id = {r["review_id"]: r for r in reviews}
    review = by_id.get(review_id) if review_id else None
    if review is None:
        review = by_id.get(_DEFAULT_REVIEW_ID) or reviews[0]

    # Both `text` AND `rating` are predictors. The text drives
    # category / assigned_to (tokens decide which support team takes
    # it); rating drives sentiment + churn_within_90d (a 1★ review is
    # a stronger churn signal than the words alone). Including both
    # surfaces the contribution of each in the popover's `$why`.
    where = {
        "text":   review["text"],
        "rating": int(review["rating"]),
    }

    body = {
        "from": "reviews",
        "where": where,
        "predict": "<varies per field>",
        "select": ["$p", "feature", {"$why": {}}],
        "limit": 5,
    }

    started = time.perf_counter()
    # 3 parallel _predict calls, same `where` body.
    with ThreadPoolExecutor(max_workers=len(PREDICT_FIELDS)) as pool:
        futures = [
            pool.submit(_predict_field, client, where, pf, label)
            for pf, label in PREDICT_FIELDS
        ]
        fields = [f.result() for f in futures]
    elapsed = int((time.perf_counter() - started) * 1000)

    product = products.get(review["product_sku"], {})

    # A small picker list of other reviews so the user can flip
    # through the queue without typing IDs.
    candidate_reviews = [
        {
            "review_id":  r["review_id"],
            "rating":     r["rating"],
            "text_short": (r["text"][:80] + "…") if len(r["text"]) > 80 else r["text"],
        }
        for r in reviews[:30]
    ]

    resp = FeedbackResponse(
        review=ReviewSummary(
            review_id=review["review_id"],
            customer_id=review["customer_id"],
            customer_short=_short_customer_name(review["customer_id"]),
            product_sku=review["product_sku"],
            product_name=product.get("name", review["product_sku"]),
            rating=int(review["rating"]),
            text=review["text"],
            created_at=review["created_at"],
            actual_category=review["category"],
            actual_sentiment=review["sentiment"],
            actual_assigned_to=review["assigned_to"],
            actual_churn_within_90d=bool(review.get("churn_within_90d", False)),
        ),
        fields=fields,
        candidate_reviews=candidate_reviews,
        last_query={"endpoint": "_predict", "body": body},
        last_response_ms=elapsed,
    )
    cache.set(cache_key, resp.to_dict(), ttl=1800)
    return resp


# ── Cache round-trip ──────────────────────────────────────────────


def _from_dict(d: dict) -> FeedbackResponse:
    return FeedbackResponse(
        review=ReviewSummary(**d["review"]),
        fields=[
            PredictedField(
                field=f["field"],
                label=f["label"],
                predicted_value=f["predicted_value"],
                confidence=f["confidence"],
                alternatives=[Alternative(**a) for a in f["alternatives"]],
                why_factors=[WhyFactor(**w) for w in f["why_factors"]],
                why_explanation=f.get("why_explanation"),
            )
            for f in d["fields"]
        ],
        candidate_reviews=d["candidate_reviews"],
        last_query=d["last_query"],
        last_response_ms=d["last_response_ms"],
    )
