"""`./do evidence personalised-search`: how much of the shopper does Aito recover?

Design, fixed before the run: docs/verification/personalised-search-prereg.md
(ADR 0037 §3). Reads only. For every scored session, six rankings over the
catalogue; each Aito ranking reads the impressions with that session left
out. Writes data/evidence/personalised-search.json: per-slice hit@10 and
MRR with 95 % intervals, the three pre-registered paired comparisons with
their sentences, and each session's first-hit ranks, so any reader can
recompute the intervals.

A run checkpoints each session to a partial file and resumes from it.
"""

from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from src.aito_client import AitoClient
from src.config import load_config
from src.evidence import result_file
from src.personalised_search import rankings as R
from src.personalised_search.bm25 import Bm25
from src.personalised_search.generator_ranking import generator_ranking
from src.personalised_search.metrics import (BM25, BM25_REFERENCE, DEPTH, GENERATOR, HISTORY, HOUSEHOLD, K,
                                             RANKINGS, SHOP, all_scores, first_hit_rank)
from src.personalised_search.sessions import Session, load_products, scored_sessions
from src.personalised_search.wording import comparison_sentence, headline, slice_label

WORKERS = 4
PARTIAL = result_file.EVIDENCE_DIR / "personalised-search.partial.jsonl"


def score_session(client: AitoClient, reference: Bm25, s: Session) -> dict:
    p = R.shop_search_p(client, s, list(R.text_lift(client, s.query)))
    ranked = {
        BM25: R.bm25_ranking(client, s),
        BM25_REFERENCE: reference.ranked(s.query),
        SHOP: R.shop_search_ranking(client, s, p),
        HISTORY: R.history_form_ranking(client, s, DEPTH),
        HOUSEHOLD: R.household_only_ranking(p),
        GENERATOR: generator_ranking(s),
    }
    return {"session": s.session_id, "slice": s.slice, "prior_orders": s.prior_orders,
            "ranks": {name: first_hit_rank(r, s.bought) for name, r in ranked.items()}}


def _resume() -> dict[str, dict]:
    if not PARTIAL.exists():
        return {}
    rows = [json.loads(line) for line in PARTIAL.read_text(encoding="utf-8").splitlines() if line]
    return {r["session"]: r for r in rows}


def run(client: AitoClient, sessions: list[Session]) -> list[dict]:
    reference = Bm25({sku: p["name"] for sku, p in load_products().items()})
    done = _resume()
    todo = [s for s in sessions if s.session_id not in done]
    print(f"{len(done)} sessions already scored, {len(todo)} to go, {WORKERS} at a time", flush=True)
    for query in sorted({s.query for s in todo}):
        R.text_lift(client, query)       # shared by every session with these words
    start = time.perf_counter()
    with PARTIAL.open("a", encoding="utf-8") as out, ThreadPoolExecutor(WORKERS) as pool:
        for i, row in enumerate(pool.map(lambda s: score_session(client, reference, s), todo), 1):
            out.write(json.dumps(row) + "\n")
            out.flush()
            done[row["session"]] = row
            if i % 100 == 0:
                rate = (time.perf_counter() - start) / i
                print(f"  {i}/{len(todo)}, {rate:.2f} s each, ~{rate * (len(todo) - i) / 60:.0f} min left", flush=True)
    return [done[s.session_id] for s in sessions]


def result(client: AitoClient, rows: list[dict]) -> dict:
    scores = all_scores(rows)
    return {
        "entry": "personalised-search",
        "data": "Synthetic",
        "adr": "ADR 0037 §3",
        "preregistration": "docs/verification/personalised-search-prereg.md",
        "script": "src/personalised_search/run.py",
        "run": {**result_file.run_info(client, "./do evidence personalised-search"),
                "sessions": len(rows), "subsample": None, "held_out": "per session (nested `from`)"},
        "metric": {"primary": f"hit@{K}", "secondary": f"MRR (reciprocal rank, 0 beyond rank {DEPTH})"},
        "rankings": list(RANKINGS),
        "headline": headline(scores[0]),
        "slices": [{**s.to_dict(), "label": slice_label(s.name),
                    "sentences": [comparison_sentence(s, c) for c in s.comparisons]} for s in scores],
        "per_session": rows,
    }


def main() -> int:
    client = AitoClient(load_config())
    sessions = scored_sessions()
    rows = run(client, sessions)
    path = result_file.write("personalised-search", result(client, rows))
    PARTIAL.unlink()
    print(f"Wrote {path}")
    for line in json.loads(path.read_text(encoding="utf-8"))["slices"]:
        print("\n".join(line["sentences"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
