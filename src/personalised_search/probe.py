"""`./do evidence personalised-search --probe`: check the query shapes before the run.

ADR 0037 §3 asks for two things before any session is scored:

1. Each ranking's query, with a nested `from` that leaves the session out,
   answers in the shape the benchmark reads (and really leaves it out).
2. `$similarity` over the name is compared with a plain Okapi BM25 in
   Python on 20 queries. If they disagree, the page names the left column
   "Aito's text similarity" rather than BM25.

Reads only. Prints what it found; `docs/verification/personalised-search-prereg.md`
records the outcome.
"""

from __future__ import annotations

import math
import random
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from src.aito_client import AitoClient
from src.config import load_config
from src.personalised_search.bm25 import Bm25
from src.personalised_search.rankings import held_out, history_form_ranking, shop_context, shop_search_p, text_lift
from src.personalised_search.sessions import load_products, scored_sessions
from src.shop_ranking import _p_true

AGREEMENT_QUERIES = 20
# The run's concurrency, and the sessions it times to choose between the
# full set and the pre-registered subsample (ADR 0037 §3, the 2-hour rule).
WORKERS = 4
TIMED_SESSIONS = 16


def check_the_session_is_left_out(client: AitoClient, session_id: str) -> None:
    res = client.search(held_out(session_id), where={"context": session_id}, limit=0)
    print(f"  rows of {session_id} inside its held-out `from`: {res['total']} (expect 0)")
    assert res["total"] == 0, "the nested `from` did not leave the session out"


def check_shapes(client: AitoClient, sessions: list) -> None:
    for s in sessions:
        lift = text_lift(client, s.query)
        p = shop_search_p(client, s, list(lift))
        print(f"  {s.session_id} “{s.query}”: {len(lift)} name matches; Shop `_recommend` returned "
              f"$p for {len(p)} (rule {s.rule}, cart {len(s.cart)} items)")
        assert set(p) <= set(lift), "the Shop's step 2 returned a product the words don't name"
        assert all(0 <= v <= 1 for v in p.values()), "a $p outside [0, 1]"
        just = client.batch([{"from": held_out(s.session_id), "where": {**shop_context(s), "product_sku": sku,
                                                                        "just_bought": True}, "predict": "purchased"}
                             for sku in list(p)[:2]])
        print(f"    just-bought re-ask, held out: P(purchased) {[round(_p_true(a, ''), 4) for a in just]}")
        ranked = history_form_ranking(client, s, 50)
        print(f"    history form: {len(ranked)} products, top 3 {ranked[:3]}")
        assert len(ranked) == 50 and len(set(ranked)) == 50, "the history form didn't return 50 distinct products"


def check_bm25_agreement(client: AitoClient, queries: list[str]) -> bool:
    """`ln($score)` at θ = 1 against the Python BM25, and their top-10 orders."""
    products = load_products()
    reference = Bm25({sku: p["name"] for sku, p in products.items()})
    same_top10, correlations = 0, []
    for q in queries:
        res = client.search("products", order_by={"$similarity": {"name": q}, "theta": 1.0},
                            select=["sku", "$score"], limit=1000)
        aito = {h["sku"]: math.log(h["$score"]) for h in res["hits"] if h["$score"] > 1.0}
        python = {sku: reference.score(q, sku) for sku in products}
        python = {k: v for k, v in python.items() if v > 0}
        both = sorted(set(aito) | set(python))
        r = _correlation([aito.get(k, 0.0) for k in both], [python.get(k, 0.0) for k in both])
        correlations.append(r)
        top_aito = sorted(aito, key=lambda k: (-round(aito[k], 6), k))[:10]
        top_python = reference.ranked(q)[:10]
        same = top_aito == top_python
        same_top10 += same
        ratio = statistics.median(aito[k] / python[k] for k in set(aito) & set(python))
        print(f"  “{q}”: {len(aito)} vs {len(python)} matched, r = {r:.4f}, "
              f"median ln($score)/bm25 = {ratio:.3f}, same top 10: {same}")
    print(f"  {same_top10}/{len(queries)} queries with the same top 10; "
          f"min r = {min(correlations):.4f}")
    agrees = same_top10 >= 18 and min(correlations) >= 0.99
    print(f"  agreement (≥ 18/20 same top 10 and r ≥ 0.99 on every query): {agrees}")
    return agrees


def time_the_run(client: AitoClient, sessions: list) -> float:
    """Wall-clock hours for every session's held-out calls, at WORKERS at a time. Scores nothing."""
    def calls(s) -> None:
        shop_search_p(client, s, list(text_lift(client, s.query)))
        history_form_ranking(client, s, 100)

    for s in sessions:
        text_lift(client, s.query)
    start = time.perf_counter()
    with ThreadPoolExecutor(WORKERS) as pool:
        list(pool.map(calls, sessions))
    return (time.perf_counter() - start) / len(sessions)


def _correlation(a: list[float], b: list[float]) -> float:
    """Pearson's r; a one-word query scores every match alike, and then
    the two agree exactly when they match the same products (r = 1)."""
    if statistics.pstdev(a) == 0 or statistics.pstdev(b) == 0:
        return 1.0 if [x > 0 for x in a] == [y > 0 for y in b] else 0.0
    return statistics.correlation(a, b)


def main() -> int:
    client = AitoClient(load_config())
    sessions = scored_sessions()
    picked = random.Random(0).sample(sessions, 6)
    print(f"0. {len(sessions)} scored sessions; Aito {client.engine_version()} on env {client._config.aito_env}")
    print("1. The nested `from` leaves the session out")
    check_the_session_is_left_out(client, picked[0].session_id)
    print("2. Each Aito ranking's shape, held out")
    check_shapes(client, picked)
    print(f"3. $similarity vs Python BM25 on {AGREEMENT_QUERIES} queries")
    queries = random.Random(1).sample(sorted({s.query for s in sessions}), AGREEMENT_QUERIES)
    check_bm25_agreement(client, queries)
    print(f"4. How long the run takes, timed on {TIMED_SESSIONS} sessions at {WORKERS} workers")
    per_session = time_the_run(client, random.Random(7).sample(sessions, TIMED_SESSIONS))
    print(f"  {per_session:.2f} s per session: {per_session * len(sessions) / 3600:.2f} h "
          f"for all {len(sessions)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
