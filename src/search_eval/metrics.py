"""Ranking metrics for the search evaluation. Pure functions, no Aito.

`ranked` is a system's result list of SKUs, best first. `labels` is the
exhaustive {sku: grade} map from `relevance.judge` (grade 1 or 2; absent
means 0). Because the labels cover the whole catalogue, the ideal ranking
for nDCG is computed from ALL relevant products, not just the retrieved
ones — so a system is penalised for what it failed to find.
"""

from __future__ import annotations

import math
import random


def dcg(gains: list[float]) -> float:
    return sum((2**g - 1) / math.log2(i + 2) for i, g in enumerate(gains))


def ndcg_at_k(ranked: list[str], labels: dict[str, int], k: int = 10) -> float:
    ideal = dcg(sorted(labels.values(), reverse=True)[:k])
    if ideal == 0:
        return 0.0
    return dcg([labels.get(s, 0) for s in ranked[:k]]) / ideal


def precision_at_k(ranked: list[str], labels: dict[str, int], k: int = 5) -> float:
    """Share of the top k that is at least partially relevant."""
    return sum(1 for s in ranked[:k] if labels.get(s, 0) > 0) / k


def recall_at_k(ranked: list[str], labels: dict[str, int], k: int = 20) -> float:
    """Share of the FULLY relevant (grade 2) products found in the top k."""
    full = {s for s, g in labels.items() if g == 2}
    if not full:
        return 0.0
    return len(full & set(ranked[:k])) / len(full)


def mrr(ranked: list[str], labels: dict[str, int]) -> float:
    """1/rank of the first fully relevant hit; 0 if none is returned."""
    for i, s in enumerate(ranked):
        if labels.get(s, 0) == 2:
            return 1.0 / (i + 1)
    return 0.0


def paired_bootstrap_ci(
    a: list[float], b: list[float], *, n_boot: int = 2000, seed: int = 0
) -> tuple[float, float, float]:
    """Mean of (b - a) over queries with a 95% bootstrap interval.

    Paired: both systems are scored on the SAME queries, so resample query
    indices and keep each query's pair together. A difference is worth
    reporting only when the interval excludes zero.
    """
    assert len(a) == len(b) and a, "need the same non-empty query set"
    d = [y - x for x, y in zip(a, b)]
    rng = random.Random(seed)
    means = sorted(
        sum(d[rng.randrange(len(d))] for _ in d) / len(d) for _ in range(n_boot)
    )
    return sum(d) / len(d), means[int(0.025 * n_boot)], means[int(0.975 * n_boot) - 1]
