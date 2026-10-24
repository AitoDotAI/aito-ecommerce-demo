"""The three classical baselines of ADR 0036, copied from Aito core's benchmark.

Source: aito-core `benchmarks/ecommerce-reco/baselines.py` at commit
625867faca (2026-10-21). The classes below are that file's text, copied,
not re-implemented, so the backtest's baseline numbers are the
benchmark's. Only the co-occurrence baseline and `grid()` are left out.
The settings the benchmark tuned and the backtest uses are in
`BASELINE_SETTINGS`.

Each baseline is `fit(fit_ids, meta, basket)` on the training orders, then
`recommend(customer, history, k)` per buyer:
- `fit_ids`: the training order ids; `meta[order] = (customer, "YYYY-MM")`;
  `basket[order]` = the order's codes;
- `history`: the buyer's training orders as `(month, codes, order)`.

Tie-breaking, kept exactly as in the source:
- Popularity: `Counter.most_common()`, so equal counts keep first-seen
  order. First-seen follows the order of `fit_ids` and of each basket's
  codes. The benchmark iterated Python sets there, whose order depends on
  the hash seed; `src/backtest_dataset.py` passes sorted tuples, so the
  order here is reproducible run to run.
- Personal repeat: each code weighs 0.5 ** (months_back / half_life) per
  order, months counted back from the latest training month; equal scores
  go to the lower code; a short list is filled from popularity.
- EASE: binary user × item matrix, diagonal zeroed (no self-recommendation),
  `np.argsort(-scores)` as in the source; a buyer with no history gets
  popularity.
"""
from __future__ import annotations
import collections

# The values the benchmark's validation chose (retail2/baselines.json
# "tuning" at 625867faca): EASE lambda 250, personal repeat half-life 6.
EASE_LAMBDA = 250
REPEAT_HALF_LIFE_MONTHS = 6


def _months_back(m, ref):
    (y1, m1), (y2, m2) = (int(m[:4]), int(m[5:7])), (int(ref[:4]), int(ref[5:7]))
    return (y2 - y1) * 12 + (m2 - m1)


class Popularity:
    name = "popularity (global)"
    def __init__(self, window=None):
        self.window = window
        if window: self.name = f"popularity (recent {window}m)"
    def fit(self, fit_ids, meta, basket):
        ref = max(meta[o][1] for o in fit_ids)
        c = collections.Counter()
        for oid in fit_ids:
            if self.window and _months_back(meta[oid][1], ref) >= self.window:
                continue
            for s in basket[oid]: c[s] += 1
        if not c:   # window too narrow -> fall back to all, loudly via name
            for oid in fit_ids:
                for s in basket[oid]: c[s] += 1
        self.ranked = [s for s, _ in c.most_common()]
        return self
    def recommend(self, customer, history, k, revealed=None):
        return self.ranked[:k]


class PersonalRepeat:
    def __init__(self, half_life=None):
        self.hl = half_life
        self.name = f"personal repeat (half-life={half_life or 'inf'})"
    def fit(self, fit_ids, meta, basket):
        self.ref = max(meta[o][1] for o in fit_ids)
        pop = collections.Counter()
        for oid in fit_ids:
            for s in basket[oid]: pop[s] += 1
        self.fallback = [s for s, _ in pop.most_common()]
        return self
    def recommend(self, customer, history, k, revealed=None):
        sc = collections.defaultdict(float)
        for m, b, _ in history:
            w = 1.0 if not self.hl else 0.5 ** (_months_back(m, self.ref) / self.hl)
            for s in b: sc[s] += w
        ranked = sorted(sc, key=lambda j: (-sc[j], j))
        if len(ranked) < k:
            ranked += [s for s in self.fallback if s not in sc][:k - len(ranked)]
        return ranked[:k]


class EASE:
    def __init__(self, lam=100.0):
        self.lam = lam
        self.name = f"EASE (lam={lam})"
    def fit(self, fit_ids, meta, basket):
        import numpy as np
        users = sorted({meta[o][0] for o in fit_ids})
        items = sorted({s for o in fit_ids for s in basket[o]})
        self.items = items
        ui = {u: i for i, u in enumerate(users)}
        ii = {s: i for i, s in enumerate(items)}
        self.ii = ii
        X = np.zeros((len(users), len(items)), dtype=np.float64)
        for oid in fit_ids:
            u = ui[meta[oid][0]]
            for s in basket[oid]:
                X[u, ii[s]] = 1.0          # binary implicit feedback
        G = X.T @ X
        G[np.diag_indices_from(G)] += self.lam
        P = np.linalg.inv(G)
        B = P / (-np.diag(P))
        B[np.diag_indices_from(B)] = 0.0   # no self-recommendation
        self.B = B
        pop = collections.Counter()
        for oid in fit_ids:
            for s in basket[oid]: pop[s] += 1
        self.fallback = [s for s, _ in pop.most_common()]
        return self
    def recommend(self, customer, history, k, revealed=None):
        import numpy as np
        src = revealed if revealed is not None else {s for _, b, _ in history for s in b}
        idx = [self.ii[s] for s in src if s in self.ii]
        if not idx: return self.fallback[:k]
        x = np.zeros(len(self.items)); x[idx] = 1.0
        sc = x @ self.B
        top = np.argsort(-sc)[:k]
        return [self.items[i] for i in top]


def baselines() -> dict[str, object]:
    """The three baselines of ADR 0036, unfitted, by report name."""
    return {
        "popularity": Popularity(),
        "personal repeat": PersonalRepeat(REPEAT_HALF_LIFE_MONTHS),
        "EASE": EASE(EASE_LAMBDA),
    }
