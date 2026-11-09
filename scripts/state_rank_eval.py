#!/usr/bin/env python3
"""ADR 0065: does ranking the month's product states, with the product as the prior, beat ranking the product? Held out by fold.

    AITO_API_URL=http://127.0.0.1:9031 AITO_API_KEY=local AITO_ENV=master PYTHONPATH=. \\
        python scripts/state_rank_eval.py load            # the full fixtures + fold and product columns, into a LOCAL engine
    ... python scripts/state_rank_eval.py run [N] [out.json]

Refuses any target but 127.0.0.1: the evaluation writes its probe columns (`context.fold`, the product's attributes on
`product_states`) and must never touch the shared instance.

Held out by fold, not by one nested `from` per session: a held-out population is a full in-heap copy of `impressions`,
so one per session fills the heap (docs/notes/2026-10-24-nested-from-batch-502-repro.md). Customers fall into FOLDS folds
by a hash of their id; a session is ranked from the other folds, so FOLDS populations are built once each.

Per variant: hit@10 (a product bought in the session is in the top 10), Brier of `$p` over the states the session showed,
that Brier split by how often a state was shown outside the session's fold (thin, mid, well), and the warm latency of the
top-10 `_recommend`.
"""
from __future__ import annotations

import hashlib
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass

from scripts.product_state_sweep import candidate_filters, context_where
from scripts.shop_query_sweep import breaks_rule, load, sample_sessions
from src.aito_client import AitoClient
from src.config import load_config

FOLDS = 5
TOP = 10
EXPOSURE_BUCKETS = (("thin", 0, 5), ("mid", 5, 30), ("well", 30, 10**9))   # showings of the state outside the fold
PRODUCT_COPY = {"p_name": ("name", "Text"), "p_tags": ("tags", "Text"), "p_category": ("category", "String"),
                "p_pet_type": ("pet_type", "String"), "p_brand": ("brand", "String")}


@dataclass(frozen=True)
class Variant:
    name: str
    target: str                       # "product_sku" or "product_state"
    based_on: tuple[str, ...] = ()
    candidates: int = TOP


VARIANTS = (
    Variant("product", "product_sku"),
    Variant("state", "product_state"),
    Variant("state basedOn sku", "product_state", ("product_sku",)),
    Variant("state basedOn product attributes", "product_state", ("p_tags", "p_category", "p_pet_type", "p_brand")),
    Variant("state basedOn sku + attributes", "product_state", ("product_sku", "p_tags", "p_category", "p_pet_type", "p_brand")),
    Variant("blend product x state", "blend", candidates=50),
    Variant("state basedOn tags", "product_state", ("p_tags",)),
    Variant("state basedOn category+pet", "product_state", ("p_category", "p_pet_type")),
    Variant("state basedOn brand", "product_state", ("p_brand",)),
    Variant("state basedOn name", "product_state", ("p_name",)),
    Variant("state basedOn tags+brand", "product_state", ("p_tags", "p_brand")),
)


def fold_of(customer_id: str) -> int:
    """The fold a customer's sessions are held out in: stable across runs and machines."""
    return int(hashlib.sha1(customer_id.encode()).hexdigest(), 16) % FOLDS


def exposure_bucket(showings: int) -> str:
    """How much evidence a state has of its own: `showings` of it outside the held-out fold."""
    return next(name for name, low, high in EXPOSURE_BUCKETS if low <= showings < high)


def held_out(fold: int) -> dict:
    """The population a fold's sessions are ranked from: every other fold's impressions."""
    return {"from": "impressions", "where": {"context.fold": {"$not": fold}}}


def brier_by_exposure(terms: list[tuple[str, float]]) -> dict[str, float]:
    """Mean squared error of `$p` per exposure bucket, from (bucket, squared error) terms."""
    by_bucket: dict[str, list[float]] = {}
    for bucket, error in terms:
        by_bucket.setdefault(bucket, []).append(error)
    return {bucket: statistics.mean(errors) for bucket, errors in by_bucket.items()}


def local_client() -> AitoClient:
    config = load_config()
    if not config.aito_api_url.startswith("http://127.0.0.1"):
        sys.exit(f"Refusing: the target is {config.aito_api_url}, not a local engine on 127.0.0.1.")
    return AitoClient(config)


def load_into_local_engine() -> None:
    """The release's fixtures, plus the probe columns: `contexts.fold`, and the product's attributes on each state."""
    from src.data_loader import SCHEMAS, create_schema, delete_table, load_fixture, upload_data
    client = local_client()
    products = {p["sku"]: p for p in load_fixture("products")}
    states = [{**s, **{col: products[s["product_sku"]][field] for col, (field, _) in PRODUCT_COPY.items()}}
              for s in load_fixture("product_states")]
    contexts = [{**c, "fold": fold_of(c["customer"]) if c.get("customer") else FOLDS} for c in load_fixture("contexts")]
    SCHEMAS["product_states"]["columns"].update({col: {"type": kind, "nullable": False, **({"analyzer": "whitespace"} if col == "p_tags" else {})}
                                                 for col, (_, kind) in PRODUCT_COPY.items()})
    SCHEMAS["contexts"]["columns"]["fold"] = {"type": "Int", "nullable": False}
    tables = {"product_states": states, "contexts": contexts}
    for table in reversed(list(SCHEMAS)):
        delete_table(client, table)
    for table, schema in SCHEMAS.items():
        create_schema(client, table, schema)
        upload_data(client, table, tables.get(table) or load_fixture(table))


def run(n_sessions: int, out_path: str) -> None:
    client = local_client()
    customers = {c["customer_id"]: c for c in load("customers")}
    products = {p["sku"]: p for p in load("products")}
    contexts_of = {c["context_id"]: c for c in load("contexts")}
    shown_total: dict[str, int] = {}
    shown_in_fold: dict[tuple[str, int], int] = {}
    for imp in load("impressions"):
        customer = contexts_of[imp["context"]].get("customer")
        shown_total[imp["product_state"]] = shown_total.get(imp["product_state"], 0) + 1
        if customer:
            key = (imp["product_state"], fold_of(customer))
            shown_in_fold[key] = shown_in_fold.get(key, 0) + 1
    only = os.environ.get("STATE_EVAL_ONLY")   # comma-separated variant names, to iterate on a few
    variants = tuple(v for v in VARIANTS if not only or v.name in only.split(","))
    results: dict[str, dict] = {v.name: {"hit": [], "ms": [], "terms": []} for v in variants}
    undeclared = 0
    for session in sample_sessions(n_sessions):
        customer = customers[session["customer"]]
        if not customer.get("pets"):
            # The query asks for the household's declared pets; most customers declare none (the Shop then
            # falls back to pets_from_orders, a different query). Counted and printed, not silently dropped.
            undeclared += 1
            continue
        fold = fold_of(session["customer"])
        for variant in variants:
            score_session(client, variant, session, customer, products, fold, shown_total, shown_in_fold, results[variant.name])
    print(f"sessions skipped, customer declares no pets: {undeclared}")
    report = {}
    for variant in variants:
        r = results[variant.name]
        ms = sorted(r["ms"])
        report[variant.name] = {"hit@10": statistics.mean(r["hit"]), "brier": statistics.mean(e for _, e in r["terms"]),
                                "brier_by_exposure": brier_by_exposure(r["terms"]),
                                "ms_median": statistics.median(ms), "ms_p95": ms[int(0.95 * (len(ms) - 1))], "sessions": len(r["hit"])}
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)
    for name, row in report.items():
        print(f"{name:40s} hit@10 {row['hit@10']:.3f}  Brier {row['brier']:.4f}  {row['ms_median']:.0f} ms (p95 {row['ms_p95']:.0f})  "
              + "  ".join(f"{b} {v:.4f}" for b, v in sorted(row["brier_by_exposure"].items())))


def asked(client, target, session, customer, fold, extra=None, limit=TOP, based_on=()):
    """One `_recommend` over the held-out population, for the product or for its state: {sku: P}."""
    via = "product_sku." if target == "product_sku" else "product_state.product_sku."
    where = {**context_where(session, customer["pets"]), **candidate_filters(session, customer["pets"], customer.get("diet"), via), **(extra or {})}
    if target == "product_state":
        where["product_state.month"] = session["month"]
    key, sku_field = ("sku", "sku") if target == "product_sku" else ("product_state_id", "product_sku")
    hits = client.recommend(held_out(fold), where, target, {"purchased": True}, select=[key, sku_field, "$p"],
                            based_on=list(based_on) or None, limit=limit)["hits"]
    return {h[sku_field]: h["$p"] for h in hits}


def score_blend(client, variant, session, customer, products, fold, shown_total, shown_in_fold, into) -> None:
    """Geometric mean of the product's P and its state's P: the product is the prior, the state adds what it has seen."""
    started = time.perf_counter()
    prior = asked(client, "product_sku", session, customer, fold, limit=variant.candidates)
    state = asked(client, "product_state", session, customer, fold, limit=variant.candidates)
    into["ms"].append((time.perf_counter() - started) * 1000)   # serial here; the Shop could ask both at once
    blended = {sku: (prior[sku] * state[sku]) ** 0.5 for sku in prior.keys() & state.keys()}
    top = sorted(blended, key=blended.get, reverse=True)[:TOP]
    bought = {r["product_sku"] for r in session["shown"] if r["purchased"]}
    into["hit"].append(int(bool(bought & set(top))))
    shown = [r for r in session["shown"] if not breaks_rule(products[r["product_sku"]], customer.get("diet"))
             and products[r["product_sku"]]["pet_type"] in customer["pets"].split()
             and r["product_sku"] not in (session.get("basket") or "").split()]
    skus = sorted({r["product_sku"] for r in shown})
    if not skus:
        return
    prior = asked(client, "product_sku", session, customer, fold, {"product_sku": {"$or": skus}}, limit=len(skus))
    state = asked(client, "product_state", session, customer, fold, {"product_state.product_sku": {"$or": skus}}, limit=len(skus))
    for r in shown:
        sku = r["product_sku"]
        if sku in prior and sku in state:
            outside = shown_total[r["product_state"]] - shown_in_fold.get((r["product_state"], fold), 0)
            into["terms"].append((exposure_bucket(outside), ((prior[sku] * state[sku]) ** 0.5 - r["purchased"]) ** 2))


def score_session(client, variant, session, customer, products, fold, shown_total, shown_in_fold, into) -> None:
    if variant.target == "blend":
        return score_blend(client, variant, session, customer, products, fold, shown_total, shown_in_fold, into)
    via = "product_sku." if variant.target == "product_sku" else "product_state.product_sku."
    where = {**context_where(session, customer["pets"]), **candidate_filters(session, customer["pets"], customer.get("diet"), via)}
    if variant.target == "product_state":
        where["product_state.month"] = session["month"]
    id_field = "sku" if variant.target == "product_sku" else "product_state_id"
    sku_of = (lambda h: h["sku"]) if variant.target == "product_sku" else (lambda h: h["product_sku"])
    select = ["sku"] if variant.target == "product_sku" else ["product_state_id", "product_sku"]
    started = time.perf_counter()
    top = client.recommend(held_out(fold), where, variant.target, {"purchased": True}, select=select,
                           based_on=list(variant.based_on) or None, limit=variant.candidates)["hits"]
    into["ms"].append((time.perf_counter() - started) * 1000)
    bought = {r["product_sku"] for r in session["shown"] if r["purchased"]}
    into["hit"].append(int(bool(bought & {sku_of(h) for h in top})))
    key = "product_sku" if variant.target == "product_sku" else "product_state"
    shown = [r for r in session["shown"] if not breaks_rule(products[r["product_sku"]], customer.get("diet"))
             and products[r["product_sku"]]["pet_type"] in customer["pets"].split()
             and r["product_sku"] not in (session.get("basket") or "").split()]
    ids = sorted({r[key] for r in shown})
    if not ids:
        return
    p = {h[id_field]: h["$p"] for h in client.recommend(held_out(fold), {**where, key: {"$or": ids}}, variant.target, {"purchased": True},
                                                       select=[id_field, "$p"], based_on=list(variant.based_on) or None, limit=len(ids))["hits"]}
    for r in shown:
        if r[key] in p:   # a state with no showing outside the fold has no row to rank (prereg of 2026-10-22)
            outside = shown_total[r["product_state"]] - shown_in_fold.get((r["product_state"], fold), 0)
            into["terms"].append((exposure_bucket(outside), (p[r[key]] - r["purchased"]) ** 2))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "load":
        load_into_local_engine()
    elif mode == "run":
        run(int(sys.argv[2]) if len(sys.argv) > 2 else 400, sys.argv[3] if len(sys.argv) > 3 else "state_rank_eval.json")
    else:
        sys.exit(__doc__)
