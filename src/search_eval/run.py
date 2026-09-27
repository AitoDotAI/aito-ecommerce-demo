"""`./do search-eval` — score every arm on the judged query set.

Writes `docs/verification/search-eval.{md,json}`: per-arm and per-stratum
nDCG@10, P@5, Recall@20, MRR, zero-result rate and latency, plus paired
bootstrap intervals for each arm against the current baseline.

Two controls, and the run fails if either misbehaves:
  - the random arm (a seeded shuffle of the catalogue) sets CHANCE level;
  - the best arm re-scored against SHUFFLED labels (each query's grades
    moved onto random products) must fall to that chance level.
The second is the one that proves the metrics reward finding relevant
products: break the link between query and labels and a good system must
become a random one.

Why not "controls must score near zero": chance is NOT near zero here.
A broad query like "kitten food" has ~200 relevant products, 30% of the
catalogue, so a random top-10 legitimately holds several. A fixed ceiling
would sit on top of that level and fail at random; the check is relative.
"""

from __future__ import annotations

import json
import random
import statistics
import sys
import time
from pathlib import Path

from src.aito_client import AitoClient
from src.config import load_config
from src.search_eval import arms as A
from src.search_eval.metrics import mrr, ndcg_at_k, paired_bootstrap_ci, precision_at_k, recall_at_k
from src.search_eval.relevance import judge, load_products, load_queries

OUT = Path(__file__).resolve().parents[2] / "docs" / "verification"
K = 20
# Shuffled labels may exceed chance by at most this much (nDCG@10) ...
CHANCE_TOLERANCE = 0.05
# ... and the best real arm must clear chance by at least this much, or
# the evaluation cannot tell a system from a shuffle at all.
MIN_SIGNAL = 0.20


def _score(ranked: list[str], labels: dict[str, int]) -> dict:
    return {"ndcg10": ndcg_at_k(ranked, labels, 10), "p5": precision_at_k(ranked, labels, 5),
            "r20": recall_at_k(ranked, labels, 20), "mrr": mrr(ranked, labels),
            "zero": 1.0 if not ranked else 0.0}


def _shuffled(labels: dict[str, int], skus: list[str], seed: str) -> dict[str, int]:
    targets = random.Random(seed).sample(skus, len(labels))
    return dict(zip(targets, labels.values()))


def run() -> int:
    client = AitoClient(load_config())
    products, queries = load_products(), load_queries()
    skus = [p["sku"] for p in products]

    live = client.search("products", limit=0)["total"]
    if live != len(products):
        print(f"ABORT: labels describe {len(products)} products, Aito holds {live}")
        return 2

    labels = {q["id"]: judge(q, products) for q in queries}
    unjudgeable = [q["id"] for q in queries if 2 not in labels[q["id"]].values()]
    if unjudgeable:
        print(f"ABORT: queries with no fully relevant product: {unjudgeable}")
        return 2

    arms: dict[str, A.Arm] = {"current_match": A.current_match, "bm25": A.bm25}
    for persona_id in ("maija", "olli", "saara"):
        arms[f"predictive[{persona_id}]"] = A.smart_search_predictive(persona_id)
    arms["random (control)"] = A.random_control(skus)
    rows, latency = {}, {}
    for name, arm in arms.items():
        rows[name], latency[name] = {}, []
        for q in queries:
            t = time.perf_counter()
            ranked = arm(client, q["q"], K)
            latency[name].append((time.perf_counter() - t) * 1000)
            rows[name][q["id"]] = {"ranked": ranked, **_score(ranked, labels[q["id"]])}

    best = max((n for n in arms if "control" not in n),
               key=lambda n: statistics.mean(r["ndcg10"] for r in rows[n].values()))
    shuffled = statistics.mean(
        ndcg_at_k(rows[best][q["id"]]["ranked"], _shuffled(labels[q["id"]], skus, q["id"]))
        for q in queries)
    random_ndcg = statistics.mean(r["ndcg10"] for r in rows["random (control)"].values())

    report = _report(queries, labels, rows, latency, best, shuffled, random_ndcg)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "search-eval.md").write_text(report["md"])
    (OUT / "search-eval.json").write_text(json.dumps(report["data"], indent=2))
    print(report["md"])

    best_ndcg = statistics.mean(r["ndcg10"] for r in rows[best].values())
    problems = []
    if shuffled > random_ndcg + CHANCE_TOLERANCE:
        problems.append(f"shuffled labels still score {shuffled:.3f} vs chance {random_ndcg:.3f}")
    if best_ndcg - random_ndcg < MIN_SIGNAL:
        problems.append(f"best arm {best_ndcg:.3f} is within {MIN_SIGNAL} of chance {random_ndcg:.3f}")
    if problems:
        print("\nCONTROL FAILURE — results are not trustworthy: " + "; ".join(problems))
        return 1
    return 0


def _report(queries, labels, rows, latency, best, shuffled, random_ndcg) -> dict:
    strata = sorted({q["stratum"] for q in queries})
    metrics = ["ndcg10", "p5", "r20", "mrr", "zero"]
    mean = lambda arm, m, ids: statistics.mean(rows[arm][i][m] for i in ids)
    ids_all = [q["id"] for q in queries]
    lines = ["# Search evaluation", "",
             f"{len(queries)} judged queries x {len(rows)} arms. Relevance is graded "
             "exhaustively from product attributes (see src/search_eval/relevance.py), "
             "never by a search system.", "",
             "| arm | nDCG@10 | P@5 | R@20 | MRR | zero-result | p50 ms | p95 ms |",
             "|:--|--:|--:|--:|--:|--:|--:|--:|"]
    for arm in rows:
        lat = sorted(latency[arm])
        lines.append(f"| {arm} | " + " | ".join(f"{mean(arm, m, ids_all):.3f}" for m in metrics)
                     + f" | {lat[len(lat)//2]:.0f} | {lat[int(len(lat)*0.95)-1]:.0f} |")
    lines += ["", "## nDCG@10 by stratum", "",
              "| stratum | " + " | ".join(rows) + " |", "|:--" + "|--:" * len(rows) + "|"]
    for s in strata:
        ids = [q["id"] for q in queries if q["stratum"] == s]
        lines.append(f"| {s} | " + " | ".join(f"{mean(a, 'ndcg10', ids):.3f}" for a in rows) + " |")
    lines += ["", "## Paired difference vs current_match (nDCG@10, 95% bootstrap CI)", ""]
    base = [rows["current_match"][i]["ndcg10"] for i in ids_all]
    for arm in rows:
        if arm == "current_match":
            continue
        d, lo, hi = paired_bootstrap_ci(base, [rows[arm][i]["ndcg10"] for i in ids_all])
        verdict = "better" if lo > 0 else "worse" if hi < 0 else "no clear difference"
        lines.append(f"- **{arm}**: {d:+.3f} [{lo:+.3f}, {hi:+.3f}] — {verdict}")
    lines += ["", "## Controls", "",
              f"- chance level (random arm): {random_ndcg:.3f} nDCG@10",
              f"- best arm (`{best}`) against SHUFFLED labels: {shuffled:.3f} "
              f"— must fall to within {CHANCE_TOLERANCE} of chance",
              f"- best arm against the real labels must clear chance by ≥ {MIN_SIGNAL}"]
    data = {"arms": {a: {q: {k: v for k, v in r.items()} for q, r in rs.items()} for a, rs in rows.items()},
            "controls": {"random_ndcg10": random_ndcg, "shuffled_labels_ndcg10": shuffled},
            "labels_size": {q: len(l) for q, l in labels.items()}}
    return {"md": "\n".join(lines) + "\n", "data": data}


if __name__ == "__main__":
    sys.exit(run())
