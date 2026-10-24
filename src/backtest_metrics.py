"""Score each method's ranked codes against what each buyer ordered (ADR 0036).

Per buyer, as in the benchmark's `retail2_run.score` (aito-core 625867faca):
- hit@1 (primary): 1 if the top code is in the buyer's test order, else 0;
- recall@10: the share of the test order's codes in the top 10. Its
  ceiling, min(10, size) / size, is what a perfect 10-slot list reaches.

Per slice of prior training orders (0, 1–2, 3+), each method's hit@1 and
Aito − best baseline are given as 95 % normal intervals over buyers
(mean ± 1.96 · SE), the difference paired buyer by buyer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

K = 10
Z_95 = 1.96
SLICES = ("0", "1–2", "3+")
AITO = "Aito"
# Baselines in report order. When two tie on the point estimate, the
# earlier, simpler one is named best (in the 0 slice EASE and personal
# repeat fall back to popularity, and "popularity" is the honest name).
BASELINE_ORDER = ("popularity", "personal repeat", "EASE")


@dataclass(frozen=True)
class Interval:
    mean: float
    low: float | None          # None when fewer than 2 buyers: no SE exists
    high: float | None

    def spans_zero(self) -> bool:
        if self.low is None or self.high is None:
            raise ValueError("An interval over fewer than 2 buyers has no bounds to compare with 0")
        return self.low <= 0 <= self.high


@dataclass(frozen=True)
class SliceResult:
    name: str
    buyers: int
    hit1: dict[str, Interval]          # per method
    recall10: dict[str, float]         # per method, point estimate
    recall10_ceiling: float
    best_baseline: str | None          # None when the slice has no buyers
    aito_minus_best: Interval | None   # None without buyers or without Aito


def slice_of(prior_orders: int) -> str:
    if prior_orders < 0:
        raise ValueError(f"A buyer cannot have {prior_orders} prior orders")
    return "0" if prior_orders == 0 else "1–2" if prior_orders <= 2 else "3+"


def hit_at_1(ranked: list[str], ordered: frozenset[str]) -> float:
    return float(bool(ranked) and ranked[0] in ordered)


def recall_at_10(ranked: list[str], ordered: frozenset[str]) -> float:
    if not ordered:
        raise ValueError("A test order with no codes cannot be scored")
    return sum(1 for code in ranked[:K] if code in ordered) / len(ordered)


def recall_ceiling(ordered: frozenset[str]) -> float:
    return min(K, len(ordered)) / len(ordered)


def mean_interval(values: list[float]) -> Interval:
    if not values:
        raise ValueError("No values: an empty slice has no estimate")
    n = len(values)
    mean = sum(values) / n
    if n < 2:
        return Interval(mean, None, None)
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)
    half = Z_95 * math.sqrt(variance / n)
    return Interval(mean, mean - half, mean + half)


def slice_results(rankings: dict[str, dict[str, list[str]]], test_codes: dict[str, frozenset[str]],
                  prior_orders: dict[str, int]) -> list[SliceResult]:
    """`rankings[method][customer]` → one result per slice, always all three."""
    for method, ranked in rankings.items():
        if ranked.keys() != test_codes.keys():
            raise ValueError(f"{method} ranked {len(ranked)} buyers, {len(test_codes)} are scored")
    baselines = [m for m in BASELINE_ORDER if m in rankings]
    if len(baselines) != len(BASELINE_ORDER):
        raise ValueError(f"Rankings hold {sorted(rankings)}; every baseline {BASELINE_ORDER} is required")
    return [_one_slice(name, sorted(c for c in test_codes if slice_of(prior_orders[c]) == name),
                       rankings, test_codes, baselines) for name in SLICES]


def _one_slice(name, customers, rankings, test_codes, baselines) -> SliceResult:
    if not customers:
        return SliceResult(name, 0, {}, {}, 0.0, None, None)
    hits = {m: [hit_at_1(rankings[m][c], test_codes[c]) for c in customers] for m in rankings}
    hit1 = {m: mean_interval(values) for m, values in hits.items()}
    best = max(baselines, key=lambda m: (hit1[m].mean, -baselines.index(m)))
    paired = None
    if AITO in rankings:
        paired = mean_interval([a - b for a, b in zip(hits[AITO], hits[best])])
    return SliceResult(
        name=name, buyers=len(customers), hit1=hit1,
        recall10={m: sum(recall_at_10(rankings[m][c], test_codes[c]) for c in customers) / len(customers)
                  for m in rankings},
        recall10_ceiling=sum(recall_ceiling(test_codes[c]) for c in customers) / len(customers),
        best_baseline=best, aito_minus_best=paired,
    )
