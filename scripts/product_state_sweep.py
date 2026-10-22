#!/usr/bin/env python3
"""ADR 0032 check B5: does recommending a product's monthly state rank better
than recommending the product? A held-out sweep. Read-only.

    AITO_ENV=observable PYTHONPATH=. python scripts/product_state_sweep.py

Design and decision rule, fixed before the run: docs/verification/
product-states-prereg.md, "B5 as run". Both variants use the Shop's "Picked
for you" context; they differ only in what `_recommend` returns. Each
session's result is appended to a checkpoint file, so a stopped run resumes
and the two variants are always paired on the same session.
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path

from scripts.shop_query_sweep import breaks_rule, load, sample_sessions
from src.aito_client import AitoClient
from src.config import load_config
from src.shop_context import rule_filter

N_SESSIONS = 1400
TOP = 10
# The pre-registered pair, and an exploratory third: the state with its product
# as the prior's feature (prereg, after B5).
VARIANTS = ("product_sku", "product_state", "product_state basedOn product_sku")
CHECKPOINT = Path(sys.argv[1] if len(sys.argv) > 1 else "product_state_sweep.jsonl")


def context_where(session: dict, pets: str) -> dict:
    """The Shop's "Picked for you" context for a session (K+ in the R1/R2 sweep)."""
    where: dict = {"context.customer.pets": {"$and": [{"$match": p} for p in pets.split()]},
                   "context.month": session["month"], "just_bought": False}
    if words := (session.get("basket_categories") or "").split():
        where["context.basket_categories"] = {"$and": [{"$match": w} for w in words]}
    return where


def candidate_filters(session: dict, pets: str, diet: str | None, via: str) -> dict:
    """Declared pets, diet rule and cart exclusion, on the product reached `via` a path."""
    filters: dict = {f"{via}pet_type": {"$or": pets.split()}}
    if (keeps_rule := rule_filter(diet)) is not None:
        # rule_filter speaks of `product_sku.*`; a state reaches the same fields one link further.
        filters.update(json.loads(json.dumps(keeps_rule).replace('"product_sku.', f'"{via}')))
    if skus := (session.get("basket") or "").split():
        filters[via.rstrip(".")] = {"$not": {"$or": skus}}
    return filters


def score(client: AitoClient, variant: str, session: dict, pets: str, diet: str | None,
          products: dict[str, dict], unseen: set[str]) -> tuple[int, float]:
    target = variant.split()[0]
    based_on = ["product_sku"] if variant.endswith("basedOn product_sku") else None
    via = "product_sku." if target == "product_sku" else "product_state.product_sku."
    where = {**context_where(session, pets), **candidate_filters(session, pets, diet, via)}
    if target == "product_state":
        where["product_state.month"] = session["month"]
    held_out = {"from": "impressions", "where": {"$not": {"context": session["context_id"]}}}
    sku_of = (lambda h: h["sku"]) if target == "product_sku" else (lambda h: h["product_sku"])
    select = ["sku"] if target == "product_sku" else ["product_state_id", "product_sku"]
    top = client.recommend(held_out, where, target, {"purchased": True}, select=select, based_on=based_on,
                           limit=TOP)["hits"]
    bought = {r["product_sku"] for r in session["shown"] if r["purchased"]}
    hit = int(bool(bought & {sku_of(h) for h in top}))

    # Calibration over what the session showed and the filters let through, on
    # states seen outside the session: an unseen state has no rows to rank
    # (prereg amendment, 2026-10-22), and both variants leave it out.
    shown = [r for r in session["shown"]
             if r["product_state"] not in unseen
             and r["product_sku"] not in (session.get("basket") or "").split()
             and not breaks_rule(products[r["product_sku"]], diet)
             and products[r["product_sku"]]["pet_type"] in pets.split()]
    if not shown:
        return hit, float("nan")
    key = "product_sku" if target == "product_sku" else "product_state"
    ids = sorted({r[key] for r in shown})
    id_field = "sku" if target == "product_sku" else "product_state_id"
    p = {h[id_field]: h["$p"] for h in client.recommend(
        held_out, {**where, key: {"$or": ids}}, target, {"purchased": True},
        select=[id_field, "$p"], based_on=based_on, limit=len(ids))["hits"]}
    if missing := [i for i in ids if i not in p]:
        raise RuntimeError(f"{target}: no $p for shown {missing[:3]} in {session['context_id']}")
    return hit, statistics.mean((p[r[key]] - r["purchased"]) ** 2 for r in shown)


def paired(a: list[float], b: list[float]) -> str:
    """Mean of b − a with a 95 % CI, over sessions where both are numbers."""
    d = [y - x for x, y in zip(a, b) if x == x and y == y]
    m, se = statistics.mean(d), statistics.stdev(d) / math.sqrt(len(d))
    return f"{m:+.4f} [{m - 1.96 * se:+.4f}, {m + 1.96 * se:+.4f}] (n = {len(d)})"


def main() -> int:
    client = AitoClient(load_config())
    customers = {c["customer_id"]: c for c in load("customers")}
    products = {p["sku"]: p for p in load("products")}
    done = {}
    if CHECKPOINT.exists():
        done = {r["session"]: r for r in map(json.loads, CHECKPOINT.read_text().splitlines())}
    sessions = sample_sessions(N_SESSIONS)
    contexts_of: dict[str, set[str]] = {}
    for imp in load("impressions"):
        contexts_of.setdefault(imp["product_state"], set()).add(imp["context"])
    with CHECKPOINT.open("a") as out:
        for i, session in enumerate(sessions, 1):
            row = done.get(session["context_id"], {"session": session["context_id"]})
            todo = [v for v in VARIANTS if v not in row]
            if todo:
                c = customers[session["customer"]]
                unseen = {r["product_state"] for r in session["shown"]
                          if contexts_of[r["product_state"]] == {session["context_id"]}}
                row["unseen_states"] = len(unseen)
                for v in todo:
                    row[v] = score(client, v, session, c["pets"], c.get("diet"), products, unseen)
                # The last line for a session wins on reading, so a resumed row replaces its earlier one.
                out.write(json.dumps(row) + "\n")
                out.flush()
                done[row["session"]] = row
            if i % 100 == 0:
                print(f"  {i}/{len(sessions)} sessions", flush=True)

    rows = [done[s["context_id"]] for s in sessions]
    print(f"unseen states left out of Brier: {sum(r.get('unseen_states', 0) for r in rows)} "
          f"in {sum(1 for r in rows if r.get('unseen_states'))} sessions")
    for metric, k in (("hit@10", 0), ("Brier", 1)):
        col = {v: [r[v][k] for r in rows] for v in VARIANTS}
        print(f"{metric}: " + "  ".join(f"{v} {statistics.mean(x for x in col[v] if x == x):.4f}" for v in VARIANTS))
        for v in VARIANTS[1:]:
            print(f"  {v} − product_sku {paired(col['product_sku'], col[v])}")
        print(f"  {VARIANTS[2]} − product_state {paired(col['product_state'], col[VARIANTS[2]])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
