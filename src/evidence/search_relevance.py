"""`./do evidence search-relevance`: the judged search evaluation, as an Evidence file.

Derives `data/evidence/search-relevance.json` from the committed report of
`./do search-eval` (`docs/verification/search-eval.json`, ADR 0026). It
runs no Aito query: the numbers are the report's, re-summarised, and the
paired intervals are recomputed with the report's own seeded bootstrap,
so they equal the Markdown report's.

What the page shows, and how it may word it (ADR 0037 §2):
- the shipped arms on 60 judged queries: nDCG@10, P@5, Recall@20, MRR;
- each column against what it replaced, and the right column against the
  left, as nDCG@10 differences with paired 95 % intervals;
- the right column's θ chosen out of sample, since it was tuned on this set;
- the controls that show the metric rewards relevance, not luck.
A difference whose interval spans 0 is "a tie".
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

from src.evidence import result_file
from src.evidence.wording import difference_sentence
from src.search_eval.metrics import paired_bootstrap_ci
from src.search_eval.relevance import load_queries
from src.search_eval.run import PERSONA_IDS, THETAS
from src.search_eval.theta_selection import out_of_sample
from src.search_service import PERSONAS, TEXT_THETA

REPORT = Path(__file__).resolve().parents[2] / "docs" / "verification" / "search-eval.json"
LEFT, BEFORE = "left: bm25", "before: $match"
METRICS = ("ndcg10", "p5", "r20", "mrr", "zero")


def right(persona: str) -> str:
    return f"right θ{TEXT_THETA}[{persona}]"


def difference(rows: dict, base: str, arm: str, ids: list[str]) -> dict:
    d, lo, hi = paired_bootstrap_ci([rows[base][i]["ndcg10"] for i in ids], [rows[arm][i]["ndcg10"] for i in ids])
    return {"difference": d, "low": lo, "high": hi}


def ndcg_sentence(arm: str, base: str, c: dict) -> str:
    shown = f"{c['difference']:+.3f} nDCG@10 [{c['low']:+.3f}, {c['high']:+.3f}]"
    return difference_sentence(arm, base, c["difference"], c["low"], c["high"], shown)


def summarise(report: dict, queries: list[dict]) -> dict:
    rows = report["arms"]
    ids = [q["id"] for q in queries]
    missing = [i for i in ids if any(i not in rows[a] for a in (BEFORE, LEFT))]
    if missing:
        raise ValueError(f"The report has no rows for judged queries {missing}: re-run ./do search-eval")
    names = {p: PERSONAS[p].label for p in PERSONA_IDS}
    shown = [BEFORE, LEFT, *(right(p) for p in PERSONA_IDS), "random (control)", "table order (control)"]
    mean = lambda arm, m, subset: statistics.mean(rows[arm][i][m] for i in subset)
    strata = sorted({q["stratum"] for q in queries})

    comparisons = [{"arm": "BM25 (left column)", "base": "$match (before)",
                    **difference(rows, BEFORE, LEFT, ids)}]
    comparisons += [{"arm": f"Right column, {names[p]}", "base": "BM25 (left column)",
                     **difference(rows, LEFT, right(p), ids)} for p in PERSONA_IDS]
    for c in comparisons:
        c["sentence"] = ndcg_sentence(c["arm"], c["base"], c)
    oos = out_of_sample(queries, rows, THETAS, PERSONA_IDS, LEFT)
    for p, c in oos["one_split"]["by_persona"].items():
        c["sentence"] = ndcg_sentence(f"Right column, {names[p]}", "BM25 (left column)", c)
    return {
        "queries": len(ids),
        "strata": {s: sum(1 for q in queries if q["stratum"] == s) for s in strata},
        "arms": [{"arm": a, **{m: mean(a, m, ids) for m in METRICS}} for a in shown],
        "by_stratum": [{"stratum": s, **{a: mean(a, "ndcg10", [q["id"] for q in queries if q["stratum"] == s])
                                         for a in shown[:5]}} for s in strata],
        "comparisons": comparisons,
        "out_of_sample": oos,
        "controls": report["controls"],
        "personas": names,
    }


def main() -> int:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    if "run" not in report:
        raise ValueError(f"{REPORT} records no run (date, env, Aito version): re-run ./do search-eval")
    summary = summarise(report, load_queries())
    result = {
        "entry": "search-relevance",
        "data": "Synthetic",
        "adr": "ADR 0026",
        "script": "src/search_eval/run.py",
        "report": "docs/verification/search-eval.md",
        "run": {**report["run"], "derived_by": "./do evidence search-relevance"},
        "theta": TEXT_THETA,
        "thetas_tried": list(THETAS),
        "headline": summary["comparisons"][0]["sentence"],
        **summary,
    }
    path = result_file.write("search-relevance", result)
    print(f"Wrote {path}")
    for c in summary["comparisons"]:
        print(c["sentence"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
