#!/usr/bin/env python3
"""Does the previous order's basket improve the Shop's ranking? A held-out sweep on throwaway branches.

    PYTHONPATH=. AITO_ENV=release2 python scripts/last_basket_sweep.py [--apply] [--sessions N]    # default: every eligible session (3,880)

Design and decision rule, fixed before the run: docs/verification/last-basket-prereg.md. Default is a
dry run: it reads the fixtures and the live row counts and writes nothing. With --apply it makes one
copy-on-write branch of env release2 per fold, deletes the fold's sessions' impressions on the branch
(never on release2 or master), ranks each held-out session with plain `_recommend` queries (no nested
`from`, so no per-session population build; core's td-20261024151214916465), and deletes the branch.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import random
import statistics
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from src.aito_client import AitoClient
from src.chained_baskets import add_columns, link_contexts, link_orders
from src.config import load_config
from src.shop_context import FOOD, RULE_WORDS, basket_words, pets_filter, rule_filter
from src.shop_ranking import LAST_ORDER_PATH, PREVIOUS_ORDER_PATH

TOP = 12
FOLDS = 5
SOURCE = "release2"
DATA = Path(__file__).resolve().parent.parent / "data"
ALL_VARIANTS = {"A": "A shop today", "B": "B + last order (cart words)", "C1": "C1 last order by link",
                "C2": "C2 two orders by link"}
# B was run 2026-10-25 (it lost); C1 and C2 are registered after it (last-basket-prereg.md), A is their control.
_picked = sys.argv[sys.argv.index("--variants") + 1].split(",") if "--variants" in sys.argv else ["A", "C1", "C2"]
VARIANTS = tuple(ALL_VARIANTS[v] for v in _picked)
apply = "--apply" in sys.argv
N_SESSIONS = int(sys.argv[sys.argv.index("--sessions") + 1]) if "--sessions" in sys.argv else 10**9   # all eligible


def load(name: str) -> list[dict]:
    return json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))


def eligible_sessions() -> list[dict]:
    """Ranked sessions of identified customers with an earlier order, a purchase, since 2025-05; seed 0."""
    contexts = {c["context_id"]: c for c in load("contexts")}
    shown: dict[str, list[dict]] = defaultdict(list)
    for imp in load("impressions"):
        shown[imp["context"]].append(imp)
    customers = {c["customer_id"]: c for c in load("customers")}
    products = {p["sku"]: p for p in load("products")}
    orders_of: dict[str, list[dict]] = defaultdict(list)
    for o in load("orders"):
        orders_of[o["customer_id"]].append(o)
    linked_orders = {o["order_id"]: o for o in link_orders(load("orders"), products)}
    linked_contexts = {c["context_id"]: c for c in link_contexts(load("contexts"), load("orders"))}
    sessions = []
    for cid, rows in sorted(shown.items()):
        ctx = contexts[cid]
        who = ctx.get("customer")
        if not who or ctx["month"] < "2025-05" or not any(r["purchased"] for r in rows):
            continue
        earlier = [o for o in orders_of[who] if o["month"] < ctx["month"]]
        if not earlier:
            continue
        last_month = max(o["month"] for o in earlier)
        last = [products[s] for o in earlier if o["month"] == last_month for s in set(o["skus"].split())]
        declared = customers[who].get("pets")
        pets = declared or " ".join(sorted({products[s]["pet_type"] for o in earlier for s in o["skus"].split()}))
        last_order = linked_orders[linked_contexts[cid]["last_order"]]
        before = linked_orders.get(last_order.get("previous_order"))
        sessions.append({**ctx, "shown": rows, "last_words": basket_words(last), "pets": pets,
                         "diet": customers[who].get("diet"),
                         "path_words": last_order["basket_categories"].split(),
                         "path2_words": before["basket_categories"].split() if before else []})
    return random.Random(0).sample(sessions, min(N_SESSIONS, len(sessions)))


def where_for(variant: str, s: dict) -> dict:
    """The Shop's "Picked for you" `where` for a session (observable-data-prereg.md, K+), and B's extra words."""
    where: dict = {"context.customer.pets": {"$and": [{"$match": p} for p in s["pets"].split()]},
                   "context.month": s["month"], "just_bought": False, **pets_filter(s["pets"])}
    words = set((s.get("basket_categories") or "").split())
    if variant == ALL_VARIANTS["B"]:
        words |= set(s["last_words"])
    if words:
        where["context.basket_categories"] = {"$and": [{"$match": w} for w in sorted(words)]}
    if variant in (ALL_VARIANTS["C1"], ALL_VARIANTS["C2"]):
        where[LAST_ORDER_PATH] = {"$and": [{"$match": w} for w in s["path_words"]]}
    if variant == ALL_VARIANTS["C2"] and s["path2_words"]:
        where[PREVIOUS_ORDER_PATH] = {"$and": [{"$match": w} for w in s["path2_words"]]}
    if (keeps_rule := rule_filter(s["diet"])) is not None:
        where.update(keeps_rule)
    if skus := (s.get("basket") or "").split():
        where["product_sku"] = {"$not": {"$or": skus}}
    return where


def score(client: AitoClient, variant: str, s: dict, products: dict[str, dict]) -> tuple[int, float]:
    where = where_for(variant, s)
    top = client.recommend("impressions", where, "product_sku", {"purchased": True}, select=["sku"], limit=TOP)["hits"]
    hit = int(bool({r["product_sku"] for r in s["shown"] if r["purchased"]} & {h["sku"] for h in top}))
    basket = (s.get("basket") or "").split()
    # The candidates the query can return: not the cart's items, not other pets' products (the
    # declared-pets filter), not food that breaks the diet (the rule filter).
    shown = [r for r in s["shown"] if r["product_sku"] not in basket
             and products[r["product_sku"]]["pet_type"] in s["pets"].split() and not (
        s["diet"] and products[r["product_sku"]]["category"] in FOOD and products[r["product_sku"]]["pet_type"] in ("dog", "cat")
        and RULE_WORDS[s["diet"]] not in products[r["product_sku"]]["name"])]
    skus = sorted({r["product_sku"] for r in shown})
    if not skus:
        return hit, float("nan")
    p = {h["sku"]: h["$p"] for h in client.recommend(
        "impressions", {**where, "product_sku": {"$or": skus}}, "product_sku", {"purchased": True},
        select=["sku", "$p"], limit=len(skus))["hits"]}
    missing = [x for x in skus if x not in p]
    if missing:
        raise RuntimeError(f"{variant}: no $p for shown {missing[:3]} in {s['context_id']}")
    return hit, statistics.mean((p[r["product_sku"]] - r["purchased"]) ** 2 for r in shown)


def checked(r: httpx.Response) -> httpx.Response:
    """The response, or a failure that carries what Aito said."""
    if r.status_code >= 400:
        raise RuntimeError(f"{r.request.method} {r.request.url.path} answered {r.status_code}: {r.text[:400]}")
    return r


def fold_of(customer: str) -> int:
    return int(hashlib.md5(customer.encode()).hexdigest(), 16) % FOLDS


Z = 1.96 if len(VARIANTS) <= 2 else 2.24    # 95 %, or 97.5 % each when two variants share a control


def paired(a: list[float], b: list[float]) -> tuple[float, float, float]:
    """Mean difference b - a with a normal-approximation interval over sessions (Z)."""
    d = [y - x for x, y in zip(a, b) if x == x and y == y]
    m, se = statistics.mean(d), statistics.stdev(d) / math.sqrt(len(d))
    return m, m - Z * se, m + Z * se


def main() -> int:
    cfg = load_config()
    products = {p["sku"]: p for p in load("products")}
    sessions = eligible_sessions()
    by_fold = defaultdict(list)
    for s in sessions:
        by_fold[fold_of(s["customer"])].append(s)
    kit = lambda s: any(p not in ("dog", "cat") for p in s["pets"].split())
    print(f"{len(sessions)} eligible sessions, {len({s['customer'] for s in sessions})} customers; "
          f"{sum(kit(s) for s in sessions)} in households with a pet other than dog or cat; "
          f"folds: {[len(by_fold[k]) for k in range(FOLDS)]}")
    if not apply:
        print("Dry run: nothing written. Re-run with --apply (makes and deletes 5 branches of", SOURCE + ").")
        return 0

    base = cfg.aito_api_url
    http = httpx.Client(headers={"x-api-key": cfg.aito_api_key, "content-type": "application/json"}, timeout=300)
    results: dict[str, list[tuple[int, float]]] = {v: [] for v in VARIANTS}
    kept: list[dict] = []
    for k in range(FOLDS):
        name = f"lb-fold-{k}"
        try:
            checked(http.post(f"{base}/api/v1/_envs", json={"name": name, "basedOn": f"env.{SOURCE}"}))
            if any(v.startswith("C") for v in VARIANTS):
                add_columns(AitoClient(dataclasses.replace(cfg, aito_env=name)),
                            {"orders": link_orders(load("orders"), products), "contexts": link_contexts(load("contexts"), load("orders"))})
            ids = [s["context_id"] for s in by_fold[k]]
            checked(http.post(f"{base}/env/{name}/api/v2/data/_delete",
                              json={"from": "impressions", "where": {"context": {"$in": ids}}}))
            client = AitoClient(dataclasses.replace(cfg, aito_env=name))
            left = client.search("impressions", where={"context": {"$or": ids}}, limit=0)["total"]
            if left:
                raise RuntimeError(f"fold {k}: {left} held-out impressions still on the branch")
            with ThreadPoolExecutor(max_workers=4) as pool:
                scored = list(pool.map(lambda s: [score(client, v, s, products) for v in VARIANTS], by_fold[k]))
            for s, row in zip(by_fold[k], scored):
                for v, res in zip(VARIANTS, row):
                    results[v].append(res)
                kept.append(s)
            print(f"  fold {k}: {len(by_fold[k])} sessions scored", flush=True)
        finally:
            http.delete(f"{base}/api/v1/_envs/{name}")
    hits = {v: [float(h) for h, _ in results[v]] for v in VARIANTS}
    brier = {v: [b for _, b in results[v]] for v in VARIANTS}
    print(f"\n{'variant':<16} {'hit@12':>8} {'Brier':>8}   (n = {len(kept)} held-out sessions)")
    for v in VARIANTS:
        print(f"{v:<16} {statistics.mean(hits[v]):>8.3f} {statistics.fmean(b for b in brier[v] if b == b):>8.4f}")
    a = VARIANTS[0]
    for b in VARIANTS[1:]:
        for label, pick in (("all", lambda s: True), ("pet other than dog/cat", kit), ("dog/cat only", lambda s: not kit(s))):
            idx = [i for i, s in enumerate(kept) if pick(s)]
            m, lo, hi = paired([hits[a][i] for i in idx], [hits[b][i] for i in idx])
            bm, blo, bhi = paired([brier[a][i] for i in idx], [brier[b][i] for i in idx])
            print(f"{b[:2]} - A, {label:<24} n={len(idx):>5}  hit@12 {m:+.3f} [{lo:+.3f}, {hi:+.3f}]  "
                  f"Brier {bm:+.4f} [{blo:+.4f}, {bhi:+.4f}]   ({"97.5" if Z > 2 else "95"} % intervals)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
