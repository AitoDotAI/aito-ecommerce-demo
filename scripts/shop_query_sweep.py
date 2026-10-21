#!/usr/bin/env python3
"""Which form of the Shop's query ranks and calibrates best? A held-out sweep. Read-only.

    AITO_ENV=observable PYTHONPATH=. python scripts/shop_query_sweep.py

Design and decision rule, fixed before the run: docs/verification/
observable-data-prereg.md, "R1/R2 as a parameter sweep". For a sample of
sessions, the Shop's `where` is rebuilt from the session's own observed
context, and every variant ranks with that session left out of the data
(a nested `from`). Scored on hit@12 (a product bought in the session is in
the top 12) and on the Brier score of `$p` over the products it showed.
"""
from __future__ import annotations

import json
import random
import statistics
import sys
from pathlib import Path

from src.aito_client import AitoClient
from src.config import load_config
from src.shop_context import FOOD, RULE_WORDS, rule_filter
from src.shop_history import missing_items

N_SESSIONS = 150
TOP = 12
DATA = Path(__file__).resolve().parent.parent / "data"
PREREGISTERED = ("A shop today", "B no absences", "C cart SKUs+words", "D basedOn pet_type", "E no customer",
                 "F customer+month")
# Exploratory, added after the pre-registered run (2026-10-20): not part of its decision rule.
EXPLORATORY = ("G declared pets", "H no customer, no absences", "K picked for you")
VARIANTS = PREREGISTERED + (EXPLORATORY if "--exploratory" in sys.argv else ())


def load(name: str) -> list[dict]:
    return json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))


def sample_sessions() -> list[dict]:
    """Sessions in the last year that showed a product someone bought, seed 0."""
    shown: dict[str, list[dict]] = {}
    for imp in load("impressions"):
        shown.setdefault(imp["context"], []).append(imp)
    contexts = {c["context_id"]: c for c in load("contexts")}
    eligible = sorted(cid for cid, rows in shown.items()
                      if any(r["purchased"] for r in rows) and contexts[cid]["month"] >= "2025-05")
    # `sample`, not a seeded `shuffle(...)[:N]`: the two draw different sessions,
    # and at n = 150 that alone moved hit@12 (prereg, correction of 2026-10-20).
    picked = random.Random(0).sample(eligible, N_SESSIONS)
    return [{**contexts[cid], "shown": shown[cid]} for cid in picked]


def variant_where(name: str, session: dict, diet: str | None, missing: list[str],
                  pets: str = "") -> tuple[dict, list[str] | None]:
    """The Shop's `where` for a session, in one variant; and its `basedOn`."""
    owned = (session.get("owned") or "").split()
    words = (session.get("basket_categories") or "").split()
    skus = (session.get("basket") or "").split()
    where: dict = {"context.customer": session["customer"], "context.month": session["month"], "just_bought": False}
    if name == "K picked for you":   # the Shop's grid after the 2026-10-21 amendment
        where = {"context.customer.pets": {"$and": [{"$match": p} for p in pets.split()]},
                 "context.month": session["month"], "just_bought": False}
        if words:
            where["context.basket_categories"] = {"$and": [{"$match": w} for w in words]}
    elif name != "F customer+month":
        if words:
            where["context.basket_categories"] = {"$and": [{"$match": w} for w in words]}
        if skus and name == "C cart SKUs+words":
            where["context.basket"] = {"$and": [{"$match": s} for s in skus]}
        if owned:
            absent = [] if name in ("B no absences", "H no customer, no absences") else missing
            where["context.owned"] = {"$and": [{"$match": t} for t in owned] + [{"$not": {"$match": t}} for t in absent]}
    if name in ("E no customer", "H no customer, no absences", "G declared pets"):
        del where["context.customer"]
    if name == "G declared pets":
        where["context.customer.pets"] = {"$and": [{"$match": p} for p in pets.split()]}
    if (keeps_rule := rule_filter(diet)) is not None:
        where.update(keeps_rule)
    if skus:
        where["product_sku"] = {"$not": {"$or": skus}}
    return where, (["pet_type"] if name == "D basedOn pet_type" else None)


def breaks_rule(product: dict, diet: str | None) -> bool:
    """Dog or cat food that breaks the household's diet, as the rule filter removes it."""
    return (diet is not None and product["category"] in FOOD and product["pet_type"] in ("dog", "cat")
            and RULE_WORDS[diet] not in product["name"])


def score(client: AitoClient, name: str, session: dict, diet: str | None, missing: list[str],
          products: dict[str, dict], pets: str) -> tuple[int, float]:
    where, based_on = variant_where(name, session, diet, missing, pets)
    held_out = {"from": "impressions", "where": {"$not": {"context": session["context_id"]}}}
    top = client.recommend(held_out, where, "product_sku", {"purchased": True}, select=["sku"],
                           based_on=based_on, limit=TOP)["hits"]
    bought = {r["product_sku"] for r in session["shown"] if r["purchased"]}
    hit = int(bool(bought & {h["sku"] for h in top}))

    # Calibration on what the session showed and the Shop could show (cart items
    # and rule-breaking food aside: the query's filter removes them by design).
    shown = [r for r in session["shown"] if r["product_sku"] not in (session.get("basket") or "").split()
             and not breaks_rule(products[r["product_sku"]], diet)]
    skus = sorted({r["product_sku"] for r in shown})
    if not skus:
        return hit, float("nan")
    restricted = {**where, "product_sku": {"$or": skus}}
    p = {h["sku"]: h["$p"] for h in client.recommend(held_out, restricted, "product_sku", {"purchased": True},
                                                      select=["sku", "$p"], based_on=based_on,
                                                      limit=len(skus))["hits"]}
    missing_p = [s for s in skus if s not in p]
    if missing_p:
        raise RuntimeError(f"{name}: no $p for shown {missing_p[:3]} in {session['context_id']}")
    brier = statistics.mean((p[r["product_sku"]] - r["purchased"]) ** 2 for r in shown)
    return hit, brier


def main() -> int:
    client = AitoClient(load_config())
    diets = {c["customer_id"]: c.get("diet") for c in load("customers")}
    products = {p["sku"]: p for p in load("products")}
    pets_of = {c["customer_id"]: c["pets"] for c in load("customers")}
    sessions = sample_sessions()
    results = {v: [] for v in VARIANTS}
    absences: dict[tuple, list[str]] = {}
    for i, session in enumerate(sessions, 1):
        owned = tuple((session.get("owned") or "").split())
        if owned not in absences:
            absences[owned] = missing_items(client, list(owned))
        for v in VARIANTS:
            results[v].append(score(client, v, session, diets[session["customer"]], absences[owned], products,
                                    pets_of[session["customer"]]))
        if i % 25 == 0:
            print(f"  {i}/{len(sessions)} sessions", flush=True)

    print(f"\n{'variant':<22} {'hit@12':>8} {'Brier':>8}   (n = {len(sessions)} held-out sessions)")
    for v in VARIANTS:
        hits = [h for h, _ in results[v]]
        briers = [b for _, b in results[v] if b == b]
        print(f"{v:<22} {statistics.mean(hits):>8.3f} {statistics.mean(briers):>8.4f}")
    # Paired against the Shop today: sessions where the variant hits and A misses, and the reverse.
    base = [h for h, _ in results[VARIANTS[0]]]
    for v in VARIANTS[1:]:
        hits = [h for h, _ in results[v]]
        win = sum(1 for a, b in zip(base, hits) if b and not a)
        loss = sum(1 for a, b in zip(base, hits) if a and not b)
        print(f"  {v:<22} vs A: +{win} / -{loss} sessions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
