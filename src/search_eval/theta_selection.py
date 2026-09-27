"""Is the right column's text weight (θ) chosen fairly? An out-of-sample check.

θ is picked on the same judged queries the report scores, so the headline
right-vs-left gain is in-sample and may flatter the choice. This repeats
the choice on half the queries (stratified: half of each stratum) and
measures the gain on the other half, over many random splits:

  - how often each θ wins on the tuning half (is the choice stable?);
  - each θ's held-out gain (where does it peak or flatten?);
  - the held-out right-vs-left gain across splits (is it still there?);
  - one split's per-persona paired interval (can 30 queries confirm it?).

The splits overlap, so their agreement shows stability, not independent
evidence.
"""

from __future__ import annotations

import random
import statistics
from collections import defaultdict

from src.search_eval.metrics import paired_bootstrap_ci

N_SPLITS = 500


def _halves(queries: list[dict], seed: int) -> tuple[list[str], list[str]]:
    by_stratum: dict[str, list[str]] = defaultdict(list)
    for q in queries:
        by_stratum[q["stratum"]].append(q["id"])
    rng = random.Random(seed)
    tune, test = [], []
    for ids in by_stratum.values():
        shuffled = sorted(ids)
        rng.shuffle(shuffled)
        tune += shuffled[: len(shuffled) // 2]
        test += shuffled[len(shuffled) // 2:]
    return tune, test


def out_of_sample_report(queries: list[dict], rows: dict, thetas: tuple, personas: tuple,
                         left_arm: str) -> list[str]:
    ndcg = lambda arm, qid: rows[arm][qid]["ndcg10"]
    right = lambda theta, p: f"right θ{theta}[{p}]"

    def right_mean(theta, ids):
        return statistics.mean(ndcg(right(theta, p), i) for p in personas for i in ids)

    def gain(theta, ids):
        return statistics.mean(ndcg(right(theta, p), i) - ndcg(left_arm, i)
                               for p in personas for i in ids)

    wins: dict = defaultdict(int)
    gains = []
    gain_by_theta: dict = defaultdict(list)
    for seed in range(N_SPLITS):
        tune, test = _halves(queries, seed)
        best = max(thetas, key=lambda t: right_mean(t, tune))
        wins[best] += 1
        gains.append(gain(best, test))
        for t in thetas:
            gain_by_theta[t].append(gain(t, test))
    gains.sort()
    lo, hi = gains[int(0.05 * N_SPLITS)], gains[int(0.95 * N_SPLITS) - 1]

    tune, test = _halves(queries, 0)
    best = max(thetas, key=lambda t: right_mean(t, tune))
    lines = ["", "## θ chosen out of sample", "",
             f"Chosen on half the queries, scored on the other half, over {N_SPLITS} "
             "stratified splits (see src/search_eval/theta_selection.py).", "",
             "- θ chosen on the tuning half: " + ", ".join(
                 f"θ{t} {wins.get(t, 0)}/{N_SPLITS}" for t in thetas),
             "- held-out right-vs-left gain for each θ (median over splits): " + ", ".join(
                 f"θ{t} {statistics.median(gain_by_theta[t]):+.3f}" for t in thetas),
             f"- held-out right-vs-left gain of the θ chosen per split: median {statistics.median(gains):+.3f}, "
             f"90 % of splits in [{lo:+.3f}, {hi:+.3f}], "
             f"positive in {sum(g > 0 for g in gains) / N_SPLITS:.0%} of splits",
             f"- one split (seed 0, θ{best}), per persona on its {len(test)} held-out queries:"]
    for p in personas:
        d, clo, chi = paired_bootstrap_ci([ndcg(left_arm, i) for i in test],
                                          [ndcg(right(best, p), i) for i in test])
        lines.append(f"  - {p}: {d:+.3f} [{clo:+.3f}, {chi:+.3f}]")
    return lines
