#!/usr/bin/env python3
""""Picked for you" for a shopper without a pet profile: identity, pets from orders, or both? Read-only.

    AITO_ENV=release2 PUBLIC_DEMO=1 PYTHONPATH=. uv run python scripts/no_profile_shop_sweep.py

Design and decision rule, fixed before the run: docs/verification/
actionable-states-prereg.md, "A sweep for the Shop" and its amendment of
2026-10-24. Each sampled session is held out of the data (a nested `from`),
ranked on arrival (an empty cart) by three forms of the Shop's `where`, and
scored on hit@12 and on the Brier score of `$p` over what it showed.
"""
from __future__ import annotations

import json
import math
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

from src.aito_client import WRITES_NONE, AitoClient, AitoError
from src.config import load_config
from src.shop_context import FOOD, RULE_WORDS, rule_filter

N_SESSIONS = int(sys.argv[1]) if len(sys.argv) > 1 else 1400   # a smaller n only to smoke-test the shapes
TOP = 12
FROM_MONTH = "2025-05"
BRIER_MARGIN = 0.01
VARIANTS = ("I", "P", "I+P")
# 3 variants × 2 queries each: 18 items a `_batch`. 90 items took 45-52 s of
# Aito time each, and the gateway answered 502 to one of them.
SESSIONS_PER_BATCH = 3
# Each session's scores, so a run that stops resumes where it stopped.
PARTIAL = Path(__file__).resolve().parent.parent / "data" / "evidence" / "no-profile-shop-sweep.partial.jsonl"
DATA = Path(__file__).resolve().parent.parent / "data"


def load(name: str) -> list[dict]:
    return json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))


def eligible_sessions() -> list[dict]:
    """Sessions from FROM_MONTH on, of a customer with no pet profile and an
    earlier order, in which something was bought."""
    customers = {c["customer_id"]: c for c in load("customers")}
    first_order: dict[str, str] = {}
    for order in load("orders"):
        first_order[order["customer_id"]] = min(first_order.get(order["customer_id"], "9999-99"), order["month"])
    shown = defaultdict(list)
    for impression in load("impressions"):
        shown[impression["context"]].append(impression)
    sessions = []
    for context in load("contexts"):
        customer = context.get("customer")
        rows = shown.get(context["context_id"], [])
        if (customer and context["month"] >= FROM_MONTH and customers[customer].get("pets") is None
                and first_order[customer] < context["month"] and any(r["purchased"] for r in rows)):
            if not context.get("pets_from_orders"):
                raise ValueError(f"{context['context_id']}: a customer with an earlier order has no pets_from_orders")
            sessions.append({**context, "shown": rows, "diet": customers[customer].get("diet")})
    return sorted(sessions, key=lambda s: s["context_id"])


def variant_where(name: str, session: dict) -> dict:
    where: dict = {"context.month": session["month"], "just_bought": False}
    pets = session["pets_from_orders"].split()
    if name in ("I", "I+P"):
        where["context.customer"] = session["customer"]
    if name in ("P", "I+P"):
        where["context.pets_from_orders"] = {"$and": [{"$match": p} for p in pets]}
        where["product_sku.pet_type"] = {"$or": pets}
    if (keeps_rule := rule_filter(session["diet"])) is not None:
        where.update(keeps_rule)
    return where


def brier_set(session: dict, products: dict[str, dict]) -> list[str]:
    """Shown products every variant may rank: the session's pets, the diet kept."""
    pets = set(session["pets_from_orders"].split())
    diet = session["diet"]

    def admitted(product: dict) -> bool:
        breaks_rule = (diet is not None and product["category"] in FOOD and product["pet_type"] in ("dog", "cat")
                       and RULE_WORDS[diet] not in product["name"])
        return product["pet_type"] in pets and not breaks_rule

    return sorted({r["product_sku"] for r in session["shown"] if admitted(products[r["product_sku"]])})


def queries_for(session: dict, skus: list[str]) -> list[dict]:
    held_out = {"from": "impressions", "where": {"$not": {"context": session["context_id"]}}}
    items = []
    for name in VARIANTS:
        where = variant_where(name, session)
        items.append({"from": held_out, "where": where, "recommend": "product_sku", "goal": {"purchased": True},
                      "limit": TOP})
        if skus:
            items.append({"from": held_out, "where": {**where, "product_sku": {"$or": skus}},
                          "recommend": "product_sku", "goal": {"purchased": True}, "limit": len(skus)})
    return items


def score(session: dict, skus: list[str], answers: list[dict]) -> dict[str, tuple[int, float | None]]:
    """Each variant's hit@12 and Brier, read from its answers in order."""
    bought = {r["product_sku"] for r in session["shown"] if r["purchased"]}
    results, answers = {}, list(answers)
    for name in VARIANTS:
        top = [h["$value"] for h in answers.pop(0)["hits"]]
        if len(top) != TOP:
            raise AitoError(f"{name} ranked {len(top)} products for {session['context_id']}, expected {TOP}")
        brier = None
        if skus:
            p = {h["$value"]: h["$p"] for h in answers.pop(0)["hits"]}
            missing = [s for s in skus if s not in p]
            if missing:
                raise AitoError(f"{name}: no $p for shown {missing[:3]} in {session['context_id']}")
            shown = [r for r in session["shown"] if r["product_sku"] in p]
            brier = statistics.mean((p[r["product_sku"]] - r["purchased"]) ** 2 for r in shown)
        results[name] = (int(bool(bought & set(top))), brier)
    return results


def paired(a: list[float], b: list[float]) -> dict:
    """Mean of a − b, with a 95 % interval over the paired differences."""
    diffs = [x - y for x, y in zip(a, b, strict=True)]
    half = 1.96 * statistics.stdev(diffs) / math.sqrt(len(diffs))
    mean = statistics.mean(diffs)
    return {"mean": mean, "low": mean - half, "high": mean + half, "n": len(diffs)}


def decide(hits: dict[str, list[int]], briers: dict[str, list[float]]) -> dict:
    mean_brier = {v: statistics.mean(briers[v]) for v in VARIANTS}
    best = min(mean_brier.values())
    eligible = [v for v in VARIANTS if mean_brier[v] <= best + BRIER_MARGIN]
    leader = max(eligible, key=lambda v: statistics.mean(hits[v]))
    reason = f"{leader} leads hit@12 among the Brier-eligible {eligible}"
    if leader != "P" and "P" in eligible:
        versus_p = paired(hits[leader], hits["P"])
        if versus_p["low"] <= 0 <= versus_p["high"]:
            return {"eligible": eligible, "choice": "P", "reason": f"{leader} − P on hit@12 includes 0: a tie goes to P"}
    if leader in ("I", "I+P") and "P" not in eligible:
        other = "I+P" if leader == "I" else "I"
        if other in eligible:
            versus = paired(hits["I+P"], hits["I"])
            if versus["low"] <= 0 <= versus["high"]:
                return {"eligible": eligible, "choice": "I", "reason": "I and I+P tie with P not eligible: the simpler I"}
    return {"eligible": eligible, "choice": leader, "reason": reason}


def main() -> int:
    config = load_config()
    if config.aito_env != "release2":
        sys.exit(f"Refusing: the sweep runs on env release2, not {config.aito_env!r}")
    client = AitoClient(config, writes=WRITES_NONE)
    products = {p["sku"]: p for p in load("products")}
    pool = eligible_sessions()
    sessions = random.Random(0).sample(pool, N_SESSIONS)
    print(f"{len(pool)} eligible sessions; {len(sessions)} sampled", flush=True)

    done = {}
    if PARTIAL.exists():
        done = {r["session"]: r["scores"] for r in map(json.loads, PARTIAL.read_text(encoding="utf-8").splitlines())}
    todo = [s for s in sessions if s["context_id"] not in done]
    print(f"{len(done)} sessions already scored, {len(todo)} to go", flush=True)
    with PARTIAL.open("a", encoding="utf-8") as out:
        for start in range(0, len(todo), SESSIONS_PER_BATCH):
            chunk = todo[start:start + SESSIONS_PER_BATCH]
            sets = [brier_set(s, products) for s in chunk]
            items = [q for s, skus in zip(chunk, sets) for q in queries_for(s, skus)]
            answers = client.batch(items)
            for s, skus in zip(chunk, sets):
                n = len(VARIANTS) * (2 if skus else 1)
                done[s["context_id"]] = score(s, skus, answers[:n])
                answers = answers[n:]
                out.write(json.dumps({"session": s["context_id"], "scores": done[s["context_id"]]}) + "\n")
            out.flush()
            if (start // SESSIONS_PER_BATCH) % 50 == 0:
                print(f"  {len(done)}/{len(sessions)} sessions", flush=True)
    results = [done[s["context_id"]] for s in sessions]

    hits = {v: [r[v][0] for r in results] for v in VARIANTS}
    with_brier = [r for r in results if r["I"][1] is not None]
    briers = {v: [r[v][1] for r in with_brier] for v in VARIANTS}
    report = {
        "engine": client.engine_version(), "env": config.aito_env,
        "eligible": len(pool), "sessions": len(results), "sessions_with_brier": len(with_brier),
        "hit_at_12": {v: statistics.mean(hits[v]) for v in VARIANTS},
        "brier": {v: statistics.mean(briers[v]) for v in VARIANTS},
        "comparisons": {
            "P − I": {"hit_at_12": paired(hits["P"], hits["I"]), "brier": paired(briers["P"], briers["I"])},
            "I+P − P": {"hit_at_12": paired(hits["I+P"], hits["P"]), "brier": paired(briers["I+P"], briers["P"])},
            "I+P − I": {"hit_at_12": paired(hits["I+P"], hits["I"]), "brier": paired(briers["I+P"], briers["I"])},
        },
        "decision": decide(hits, briers),
    }
    print(json.dumps(report, indent=2))
    PARTIAL.unlink()
    return 0


if __name__ == "__main__":
    sys.exit(main())
