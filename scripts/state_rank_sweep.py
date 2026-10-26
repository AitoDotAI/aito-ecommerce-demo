#!/usr/bin/env python3
"""Does re-scoring the Shop's ranking by the month's product state improve it? A held-out sweep.

    PYTHONPATH=. AITO_ENV=release2 python scripts/state_rank_sweep.py [--apply] [--sessions N]

Design and decision rule, fixed before the run: docs/verification/state-rank-prereg.md. It reuses the
last-basket sweep's sessions, folds and throwaway branches (scripts/last_basket_sweep.py): one branch of
release2 per fold, the fold's sessions' impressions deleted on the branch, so the shop-wide lifts it reads
are learned without the held-out sessions. Default is a dry run that reads the fixtures and writes nothing.
"""
from __future__ import annotations

import dataclasses
import statistics
import sys
from collections import defaultdict

import httpx

from scripts.last_basket_sweep import (ALL_VARIANTS, FOLDS, SOURCE, apply, candidate_rows, checked, eligible_sessions,
                                       fold_of, load, paired_at, recommend_many, where_for)
from src.aito_client import AitoClient
from src.config import load_config
from src.shop_rescore import adjustment, previous_month, STATE_MODES
from src.shop_state_lifts import StateLifts, read_state_lifts

TOP = 12
CANDIDATES = 40         # what the Shop re-scores
CONTROL = ALL_VARIANTS["A"]
BRANCH = "sr-fold"


def state_rows() -> dict[tuple[str, str], dict]:
    return {(r["product_sku"], r["month"]): r for r in load("product_states")}


def factor(mode: str, sku: str, month: str, states: dict, lifts: StateLifts) -> float:
    """The Shop's re-score factor for a product in a session's month (src/shop_rescore.py, `state_rescore`)."""
    now = states[(sku, month)]
    last = states.get((sku, previous_month(month)), now)
    if mode == "offer":
        return adjustment(1.0, now, {"rating_band": now["rating_band"]}, lifts).score
    return adjustment(1.0, now, last, lifts, offer_against=last["discount_band"]).score


def score_fold(client: AitoClient, sessions: list[dict], products: dict, states: dict) -> dict[str, list[tuple[int, float]]]:
    """(hit@12, Brier) per session, for the control and each state mode, from the same two reads as the last-basket sweep."""
    lifts = read_state_lifts(client)
    wheres = [where_for(CONTROL, s) for s in sessions]
    ranked = recommend_many(client, [{"from": "impressions", "where": w, "recommend": "product_sku",
                                      "goal": {"purchased": True}, "limit": CANDIDATES} for w in wheres])
    shown = [candidate_rows(s, products) for s in sessions]
    sku_lists = [sorted({r["product_sku"] for r in rows}) for rows in shown]
    asked = [i for i, skus in enumerate(sku_lists) if skus]
    restricted = recommend_many(client, [{"from": "impressions", "where": {**wheres[i], "product_sku": {"$or": sku_lists[i]}},
                                          "recommend": "product_sku", "goal": {"purchased": True},
                                          "limit": len(sku_lists[i])} for i in asked])
    p_of = {i: {h["$value"]: h["$p"] for h in hits} for i, hits in zip(asked, restricted)}
    out: dict[str, list[tuple[int, float]]] = {m: [] for m in ("control", *STATE_MODES)}
    for i, (sess, hits) in enumerate(zip(sessions, ranked)):
        bought = {r["product_sku"] for r in sess["shown"] if r["purchased"]}
        for mode in out:
            f = (lambda sku: 1.0) if mode == "control" else (lambda sku, m=mode: factor(m, sku, sess["month"], states, lifts))
            top = sorted(hits, key=lambda h: -h["$p"] * f(h["$value"]))[:TOP]
            hit = int(bool(bought & {h["$value"] for h in top}))
            if i not in p_of:
                out[mode].append((hit, float("nan")))
                continue
            # A re-scored number is read as a probability, capped at 1, so Brier says whether it is a calibrated one.
            brier = statistics.mean((min(1.0, p_of[i][r["product_sku"]] * f(r["product_sku"])) - r["purchased"]) ** 2
                                    for r in shown[i])
            out[mode].append((hit, brier))
    return out


def main() -> int:
    cfg = load_config()
    products = {p["sku"]: p for p in load("products")}
    states = state_rows()
    sessions = eligible_sessions()
    by_fold = defaultdict(list)
    for s in sessions:
        by_fold[fold_of(s)].append(s)
    print(f"{len(sessions)} eligible sessions; folds: {[len(by_fold[k]) for k in range(FOLDS)]}")
    if not apply:
        print("Dry run: nothing written. Re-run with --apply (makes and deletes 5 branches of", SOURCE + ").")
        return 0

    base = cfg.aito_api_url
    http = httpx.Client(headers={"x-api-key": cfg.aito_api_key, "content-type": "application/json"}, timeout=300)
    results: dict[str, list[tuple[int, float]]] = {m: [] for m in ("control", *STATE_MODES)}
    kept: list[dict] = []
    for k in range(FOLDS):
        name = f"{BRANCH}-{k}"
        try:
            checked(http.post(f"{base}/api/v1/_envs", json={"name": name, "basedOn": f"env.{SOURCE}"}))
            ids = [s["context_id"] for s in by_fold[k]]
            checked(http.post(f"{base}/env/{name}/api/v2/data/_delete",
                              json={"from": "impressions", "where": {"context": {"$in": ids}}}))
            client = AitoClient(dataclasses.replace(cfg, aito_env=name))
            left = client.search("impressions", where={"context": {"$or": ids}}, limit=0)["total"]
            if left:
                raise RuntimeError(f"fold {k}: {left} held-out impressions still on the branch")
            for mode, rows in score_fold(client, by_fold[k], products, states).items():
                results[mode].extend(rows)
            kept.extend(by_fold[k])
            print(f"  fold {k}: {len(by_fold[k])} sessions scored", flush=True)
        finally:
            http.delete(f"{base}/api/v1/_envs/{name}")

    hits = {m: [float(h) for h, _ in rows] for m, rows in results.items()}
    brier = {m: [b for _, b in rows] for m, rows in results.items()}
    print(f"\n{'variant':<10} {'hit@12':>8} {'Brier':>8}   (n = {len(kept)} held-out sessions)")
    for m in results:
        print(f"{m:<10} {statistics.mean(hits[m]):>8.3f} {statistics.fmean(b for b in brier[m] if b == b):>8.4f}")
    for mode in STATE_MODES:
        d, lo, hi = paired_at(2.24, hits["control"], hits[mode])
        bd, blo, bhi = paired_at(2.24, brier["control"], brier[mode])
        print(f"{mode} - control  hit@12 {d:+.3f} [{lo:+.3f}, {hi:+.3f}]  Brier {bd:+.4f} [{blo:+.4f}, {bhi:+.4f}]   (97.5 % intervals)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
