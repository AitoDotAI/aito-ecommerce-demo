"""Scores and paired intervals for the personalised-search benchmark (ADR 0037 §3).

Per session, each ranking is kept as the rank of the first product bought
in that session (None when none is in the ranked depth). From it:
- hit@10 (primary): 1 if a bought product is in the top 10;
- reciprocal rank (secondary, MRR as its mean): 1 / that rank, 0 beyond DEPTH.

Intervals are 95 % normal intervals over sessions, mean ± 1.96 · SE, as in
ADR 0036; a difference is paired session by session.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from src.backtest_metrics import Interval, mean_interval
from src.personalised_search.sessions import SLICES

K = 10
DEPTH = 100
TOO_FEW_TO_READ = 30
ALL = "all"

BM25 = "BM25"
BM25_REFERENCE = "BM25, reference"
SHOP = "Aito, the Shop's search"
HISTORY = "Aito, with the shopper's history"
HOUSEHOLD = "Household only"
GENERATOR = "Generator's ranking"
RANKINGS = (BM25, BM25_REFERENCE, SHOP, HISTORY, HOUSEHOLD, GENERATOR)
# Ties on the point estimate go to the earlier one: the shipped search first.
AITO_RANKINGS = (SHOP, HISTORY, HOUSEHOLD)


def first_hit_rank(ranked: list[str], bought: frozenset[str]) -> int | None:
    for rank, sku in enumerate(ranked[:DEPTH], 1):
        if sku in bought:
            return rank
    return None


def hit_at_10(rank: int | None) -> float:
    return float(rank is not None and rank <= K)


def reciprocal_rank(rank: int | None) -> float:
    return 0.0 if rank is None else 1.0 / rank


@dataclass(frozen=True)
class Comparison:
    """hit@10 of `ranking` − hit@10 of `against`, paired over a slice's sessions."""
    ranking: str
    against: str
    difference: Interval


@dataclass(frozen=True)
class SliceScores:
    name: str
    sessions: int
    hit10: dict[str, Interval]
    mrr: dict[str, Interval]
    best_aito: str
    comparisons: list[Comparison]

    def to_dict(self) -> dict:
        return asdict(self)


def best_aito(hit10: dict[str, Interval]) -> str:
    return max(AITO_RANKINGS, key=lambda r: (hit10[r].mean, -AITO_RANKINGS.index(r)))


def slice_scores(name: str, rows: list[dict]) -> SliceScores:
    """`rows`: one per session, {"ranks": {ranking: first-hit rank or None}}."""
    hits = {r: [hit_at_10(row["ranks"][r]) for row in rows] for r in RANKINGS}
    hit10 = {r: mean_interval(hits[r]) for r in RANKINGS}
    mrr = {r: mean_interval([reciprocal_rank(row["ranks"][r]) for row in rows]) for r in RANKINGS}
    best = best_aito(hit10)

    def paired(a: str, b: str) -> Comparison:
        return Comparison(a, b, mean_interval([x - y for x, y in zip(hits[a], hits[b])]))

    return SliceScores(name, len(rows), hit10, mrr, best,
                       [paired(SHOP, BM25), paired(HISTORY, SHOP), paired(GENERATOR, best)])


def all_scores(rows: list[dict]) -> list[SliceScores]:
    """Every session, then each history slice that has sessions."""
    scores = [slice_scores(ALL, rows)]
    for name in SLICES:
        in_slice = [row for row in rows if row["slice"] == name]
        if in_slice:
            scores.append(slice_scores(name, in_slice))
    return scores
