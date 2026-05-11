"""Evaluation — honest pass/fail across four `_evaluate` calls.

One of the four models (Return Risk) deliberately fails its
threshold — the fixture's ~3 % returned share gives Aito no
features that beat the prior. That's the demo's "Aito tells you
when it doesn't know" moment per ADR 0010.

Cached for 1 hour. Each evaluate call takes 5-15 s live; running
all four sequentially would be ~40 s, so we parallelise.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

from src.aito_client import AitoClient
from src import cache


# Lift threshold for pass/fail in **percentage points**.
PASS_THRESHOLD_PP = 10.0


# ── Model configuration ───────────────────────────────────────────


@dataclass(frozen=True)
class ModelSpec:
    id: str
    label: str
    table: str
    where: dict
    predict: str
    feature_labels: list[str]


MODELS: list[ModelSpec] = [
    ModelSpec(
        id="pet_type_from_name",
        label="Pet type from product name",
        table="products",
        where={"name": {"$get": "name"}, "brand": {"$get": "brand"}},
        predict="pet_type",
        feature_labels=["name", "brand"],
    ),
    ModelSpec(
        id="dietary_from_name",
        label="Dietary tag from product attributes",
        table="products",
        where={
            "name":     {"$get": "name"},
            "brand":    {"$get": "brand"},
            "category": {"$get": "category"},
            "pet_type": {"$get": "pet_type"},
        },
        predict="dietary",
        feature_labels=["name", "brand", "category", "pet_type"],
    ),
    ModelSpec(
        id="segment_from_product",
        label="Customer segment from product attributes",
        table="order_lines",
        where={
            "product_sku.pet_type": {"$get": "product_sku.pet_type"},
            "product_sku.category": {"$get": "product_sku.category"},
        },
        predict="customer_segment",
        feature_labels=["product.pet_type", "product.category"],
    ),
    ModelSpec(
        id="return_risk",
        label="Return risk (deliberate honest-failure case)",
        table="order_lines",
        where={
            "product_sku.category": {"$get": "product_sku.category"},
            "product_sku.pet_type": {"$get": "product_sku.pet_type"},
            "customer_segment":     {"$get": "customer_segment"},
        },
        predict="returned",
        feature_labels=["product.category", "product.pet_type", "customer_segment"],
    ),
]


# ── DTOs ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EvalResult:
    id: str
    label: str
    table: str
    predict: str
    features: list[str]
    accuracy: float
    base_accuracy: float
    accuracy_gain: float
    n: int
    threshold_pp: float
    verdict: str         # "pass" | "fail"
    last_query: dict
    error: str | None    # populated when Aito returned 5xx; nothing else set


@dataclass
class EvalResponse:
    models: list[EvalResult]
    last_run: str
    total_response_ms: int

    def to_dict(self) -> dict:
        return {
            "models":            [asdict(m) for m in self.models],
            "last_run":          self.last_run,
            "total_response_ms": self.total_response_ms,
        }


# ── Live evaluate ─────────────────────────────────────────────────


def _evaluate_one(client: AitoClient, model: ModelSpec) -> EvalResult:
    body = {
        "testSource": {"from": model.table, "limit": 200},
        "evaluate": {
            "from":    model.table,
            "where":   model.where,
            "predict": model.predict,
        },
        "select": ["accuracy", "baseAccuracy", "n"],
    }
    try:
        res = client.evaluate(model.table, model.where, model.predict, test_limit=200)
    except Exception as exc:
        return EvalResult(
            id=model.id, label=model.label, table=model.table,
            predict=model.predict, features=model.feature_labels,
            accuracy=0.0, base_accuracy=0.0, accuracy_gain=0.0,
            n=0, threshold_pp=PASS_THRESHOLD_PP, verdict="fail",
            last_query={"endpoint": "_evaluate", "body": body},
            error=str(exc)[:200],
        )

    accuracy = float(res.get("accuracy", 0) or 0)
    base = float(res.get("baseAccuracy", 0) or 0)
    # Prefer Aito's own gain field if present; fall back to acc - base.
    gain = float(res.get("accuracyGain", accuracy - base) or 0)
    n = int(res.get("n", 0))
    verdict = "pass" if (gain * 100) >= PASS_THRESHOLD_PP else "fail"

    return EvalResult(
        id=model.id, label=model.label, table=model.table,
        predict=model.predict, features=model.feature_labels,
        accuracy=round(accuracy, 4),
        base_accuracy=round(base, 4),
        accuracy_gain=round(gain, 4),
        n=n,
        threshold_pp=PASS_THRESHOLD_PP,
        verdict=verdict,
        last_query={"endpoint": "_evaluate", "body": body},
        error=None,
    )


# ── Public entry point ────────────────────────────────────────────


def run_evaluation(client: AitoClient) -> EvalResponse:
    cached = cache.get("evaluation:run")
    if cached:
        return _from_dict(cached)

    started = time.perf_counter()
    # Parallelise the four `_evaluate` calls — each takes 5-15 s
    # live; serial would be ~40 s.
    with ThreadPoolExecutor(max_workers=len(MODELS)) as pool:
        results = list(pool.map(lambda m: _evaluate_one(client, m), MODELS))
    elapsed = int((time.perf_counter() - started) * 1000)

    resp = EvalResponse(
        models=results,
        last_run=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        total_response_ms=elapsed,
    )
    cache.set("evaluation:run", resp.to_dict(), ttl=3600)
    return resp


def _from_dict(d: dict) -> EvalResponse:
    return EvalResponse(
        models=[EvalResult(**m) for m in d["models"]],
        last_run=d["last_run"],
        total_response_ms=d["total_response_ms"],
    )
