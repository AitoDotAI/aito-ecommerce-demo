#!/usr/bin/env python3
"""The Experiments page's evidence (ADR 0064): each experiment's arms, and whether choosing per person pays. Writes data/evidence/experiments.json.

    PYTHONPATH=. uv run python scripts/experiments_evidence.py                       # dry run: says what it would read and write
    ./do env-new experiments-evidence --apply                                         # once: a branch of master for the held-out check
    AITO_ENV=<env with the experiments tables> PYTHONPATH=. uv run python scripts/experiments_evidence.py --apply

The arms are counted in the env named by AITO_ENV. Whether a per-person choice pays is measured apart: a branch `experiments-evidence` is loaded with the
showings **except the last month**, Aito chooses the arm for each held-out shopper and product from the shopper's signal, and the choice is scored against the
generator's true purchase chances (data/answer_key/experiment_chances.json). A real shop would run the same comparison as a held-out group.
"""
from __future__ import annotations

import dataclasses
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

from data.experiments import ARMS, KINDS
from src.aito_client import AitoClient
from src.config import load_config
from src.data_loader import create_schema, delete_table, optimize_table, upload_data
from src.experiment_stats import arm_figures, bootstrap_gain, personal_choice_verdict, profit_difference, verdict
from src.schema import SCHEMAS

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SCRATCH = "experiments-evidence"
TABLES = ("experiments", "experiment_variants", "experiment_showings")
PAIRS = 1500            # held-out (shopper, experiment) pairs scored per kind
BATCH = 100
SEED = 64


def load(name: str):
    return json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))


def chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def counts(client: AitoClient, wheres: list[dict]) -> list[int]:
    return [a["total"] for part in chunks([{"from": "experiment_showings", "where": w, "limit": 0} for w in wheres], BATCH) for a in client.batch(part)]


def experiment_entries(client: AitoClient, experiments: list[dict], variants: list[dict], names: dict[str, str]) -> list[dict]:
    """Per experiment its arms (showings, purchases, profit per showing), the difference of the second arm from the control and what to do next."""
    shown = counts(client, [{"variant": v["variant_id"]} for v in variants])
    bought = counts(client, [{"variant": v["variant_id"], "purchased": True} for v in variants])
    by_variant = {v["variant_id"]: (v, s, b) for v, s, b in zip(variants, shown, bought)}
    out = []
    for e in experiments:
        arms = []
        for arm in ARMS[e["kind"]]:
            variant, s, b = by_variant[f"{e['experiment_id']}:{arm}"]
            arms.append({"arm": arm, "is_control": variant["is_control"], "price_eur": variant["price_eur"], "margin_eur": variant["margin_eur"],
                         "title": variant["title"], "image": variant["image"], **arm_figures(s, b, variant["margin_eur"])})
        row = {**e, "product": names[e["product_sku"]], "arms": arms, "difference": None, "verdict": None}
        if e["status"] != "draft":
            first, second = arms
            row["difference"] = profit_difference((first["showings"], first["purchases"]), (second["showings"], second["purchases"]), first["margin_eur"], second["margin_eur"])
            row["verdict"] = verdict(row["difference"])
        out.append(row)
    return out


def load_training(client: AitoClient, held_out: str) -> None:
    if client.env != SCRATCH:
        raise SystemExit(f"Refusing to write: AITO_ENV for the held-out check is {client.env!r}, not {SCRATCH!r}")
    rows = {"experiments": load("experiments"), "experiment_variants": load("experiment_variants"),
            "experiment_showings": [s for s in load("experiment_showings") if s["month"] < held_out]}
    for table in reversed(TABLES):
        delete_table(client, table)
    for table in TABLES:
        create_schema(client, table, SCHEMAS[table])
        upload_data(client, table, rows[table])
        optimize_table(client, table)


def per_person(client: AitoClient, kind: str, experiments: list[dict], variants: list[dict], held_out: str) -> dict:
    """How the shop's signal relates to the reaction to the second arm, and what choosing per person earns on the held-out month."""
    mine = {e["experiment_id"]: e for e in experiments if e["kind"] == kind and e["status"] != "draft"}
    margin = {v["variant_id"]: v["margin_eur"] for v in variants}
    first, second = ARMS[kind]
    showings = [s for s in load("experiment_showings") if s["experiment"] in mine]
    train = [s for s in showings if s["month"] < held_out]
    levels = sorted({s["signal"] for s in train})
    lift = []
    for level in levels:
        row = {"signal": level}
        for arm in (first, second):
            rows = [s for s in train if s["signal"] == level and s["variant"].endswith(f":{arm}")]
            row[arm] = {"showings": len(rows), "rate": sum(s["purchased"] for s in rows) / len(rows) if rows else None}
        row["lift"] = row[second]["rate"] / row[first]["rate"] if row[first]["rate"] else None
        lift.append(row)
    # What a plain A/B test decides: per experiment the arm with the higher profit per showing over everybody, from the training months.
    seen, sold = defaultdict(int), defaultdict(int)
    for s in train:
        seen[s["variant"]] += 1
        sold[s["variant"]] += s["purchased"]
    winner = {eid: max((f"{eid}:{a}" for a in ARMS[kind]), key=lambda v: sold[v] / seen[v] * margin[v]) for eid in mine}
    pairs = sorted({(s["customer"], s["experiment"], s["signal"]) for s in showings if s["month"] == held_out})
    pairs = random.Random(SEED).sample(pairs, min(PAIRS, len(pairs)))
    queries = [{"from": "experiment_showings", "where": {"signal_arm": f"{signal}|{arm}", "product_sku": mine[eid]["product_sku"]}, "predict": "purchased", "limit": 2}
               for _, eid, signal in pairs for arm in (first, second)]
    answers = [a for part in chunks(queries, BATCH) for a in client.batch(part)]
    chance = json.loads((DATA / "answer_key" / "experiment_chances.json").read_text())
    per_customer = defaultdict(list)
    totals = defaultdict(float)
    for i, (customer, eid, _) in enumerate(pairs):
        p = [next(h["$p"] for h in answers[2 * i + k]["hits"] if h["$value"] is True) for k in (0, 1)]
        true = chance[eid][customer]
        value = lambda k: true[k] * margin[f"{eid}:{(first, second)[k]}"]
        picked = max((0, 1), key=lambda k: p[k] * margin[f"{eid}:{(first, second)[k]}"])
        plain = (first, second).index(winner[eid].split(":")[1])
        per_customer[customer].append((value(plain), value(picked)))
        totals["control"] += value(0)
        totals["winner"] += value(plain)
        totals["personal"] += value(picked)
        totals["oracle"] += max(value(0), value(1))
    n = len(pairs)
    result = {**bootstrap_gain(per_customer, random.Random(SEED)), "pairs": n, "profit_per_showing": {k: v / n for k, v in totals.items()}}
    gap = result["profit_per_showing"]["oracle"] - result["profit_per_showing"]["winner"]
    result["share_of_gap"] = (result["profit_per_showing"]["personal"] - result["profit_per_showing"]["winner"]) / gap if gap else None
    # What a perfect signal would earn over the plain winner, to set beside what the shop's signal earns.
    result["ceiling_gain_percent"] = 100 * gap / result["profit_per_showing"]["winner"]
    result["verdict"] = personal_choice_verdict(result)
    return {"signal": next(iter(mine.values()))["signal"], "levels": lift, "experiments": sorted(mine), "held_out_month": held_out, **result}


def main(argv: list[str]) -> int:
    experiments, variants, products = load("experiments"), load("experiment_variants"), load("products")
    held_out = max(s["month"] for s in load("experiment_showings"))
    if "--apply" not in argv:
        print(f"Dry run: would count {len(variants)} variants in env {load_config().aito_env!r}, load the showings before {held_out} into env {SCRATCH!r} "
              f"and score {PAIRS} held-out pairs per kind ({', '.join(KINDS)}); writes data/evidence/experiments.json. Re-run with --apply.")
        return 0
    config = load_config()
    release, scratch = AitoClient(config), AitoClient(dataclasses.replace(config, aito_env=SCRATCH))
    names = {p["sku"]: p["name"] for p in products}
    out = {"months": sorted({s["month"] for s in load("experiment_showings")}), "held_out_month": held_out,
           "experiments": experiment_entries(release, experiments, variants, names)}
    load_training(scratch, held_out)
    out["per_person"] = {kind: per_person(scratch, kind, experiments, variants, held_out) for kind in KINDS}
    (DATA / "evidence").mkdir(exist_ok=True)
    (DATA / "evidence" / "experiments.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: {x: v[x] for x in ("signal", "gain_percent", "interval_percent", "share_of_gap", "verdict")} for k, v in out["per_person"].items()}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
