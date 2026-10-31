"""The weekly win-back run, as stored data (ADR 0052).

A run is the agent's pass over Retention's at-risk customers. It reads the retention snapshot the
Retention page serves, so a run and the page cannot disagree, and keeps for each customer the facts a
step shows: the best action, its lift, its expected net, and how many rows of the shop's history
that action has in the customer's exact situation. The gate's outcome is not stored: it is decided
when a run is read, with the store's settings (`shopkeeper_gate.py`).

`build_winback_run` is deterministic over the snapshot; a test rebuilds it and compares it with the file
in `data/agent_runs/`, so a stored run that has fallen behind the snapshot fails loudly.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from src.shopkeeper_gate import ACT, NEVER_AUTO, QUIET, SUGGEST, GateSettings, decide

ROOT = Path(__file__).resolve().parent.parent
RETENTION_SNAPSHOT = ROOT / "data" / "precomputed" / "v2-master" / "retention.json"
CUSTOMER_ACTIONS = ROOT / "data" / "customer_actions.json"
RELEASE_ENV = ROOT / "data" / "release-env.json"
RUNS_DIR = ROOT / "data" / "agent_runs"
CONTEXT_FIELDS = ("recency_bucket", "spend_band", "offer_buyer", "open_issue", "email_history", "tracking_consent")
ROOT_CAUSES_KEPT = 2


def release_env() -> str:
    return json.loads(RELEASE_ENV.read_text())["env"]


def rows_by_situation() -> Counter:
    """How often the shop did each action in each exact situation: the rows an option's lift rests on."""
    return Counter((tuple(r[f] for f in CONTEXT_FIELDS), r["action"]) for r in json.loads(CUSTOMER_ACTIONS.read_text()))


def build_winback_run(snapshot: dict, rows_by_situation: Counter, release: str) -> dict:
    steps = []
    for customer in snapshot["at_risk"]:
        actions = customer["actions"]
        context = actions["context"]
        best, none = actions["options"][0], next(o for o in actions["options"] if o["action"] == "none")
        situation = tuple(context[f] for f in CONTEXT_FIELDS)
        steps.append({
            "customer_id": customer["customer_id"], "name": customer["name"], "risk": customer["risk"],
            "spend_12m_eur": customer["spend_12m_eur"], "tells": customer["tells"], "context": context,
            "order_value_eur": actions["order_value_eur"],
            "best": {k: best[k] for k in ("action", "label", "purchase_p", "purchase_lift_p", "net_vs_none_eur", "cost_eur")},
            "none_purchase_p": none["purchase_p"],
            "rows": rows_by_situation[(situation, best["action"])],
            "rows_no_action": rows_by_situation[(situation, "none")],
            "alternatives": [{k: o[k] for k in ("label", "purchase_p", "purchase_lift_p", "net_vs_none_eur")}
                             for o in actions["options"][1:]],
        })
    return {
        "id": "winback", "routine": "winback", "title": "Weekly win-back run",
        "release": release, "as_of_month": snapshot["as_of_month"], "simulated": True,
        "source": "data/precomputed/v2-master/retention.json (the data Retention serves)",
        "steps": steps,
        "root_causes": {"tells": snapshot["tells"][:ROOT_CAUSES_KEPT],
                        "drivers": [d for d in snapshot["drivers"] if d["lift"] > 1][:1]},
    }


def decide_steps(run: dict, settings: GateSettings) -> list[dict]:
    """Every step with the gate's outcome under `settings`."""
    decided = []
    for step in run["steps"]:
        best = step["best"]
        decision = decide(best["action"], best["label"], best["purchase_lift_p"], best["net_vs_none_eur"], step["rows"], settings)
        decided.append({**step, "outcome": decision.outcome, "reason": decision.reason})
    return decided


def tally(decided: list[dict]) -> dict:
    """The run's headline: steps per outcome, and the expected euros over doing nothing that each group holds."""
    summary = {outcome: {"steps": 0, "expected_net_eur": 0.0} for outcome in (ACT, SUGGEST, NEVER_AUTO, QUIET)}
    for step in decided:
        group = summary[step["outcome"]]
        group["steps"] += 1
        if step["outcome"] != QUIET:
            group["expected_net_eur"] = round(group["expected_net_eur"] + step["best"]["net_vs_none_eur"], 2)
    return summary


def load_run(run_id: str) -> dict:
    path = RUNS_DIR / f"{run_id}.json"
    if not path.is_file():
        raise FileNotFoundError(f"No stored run {run_id!r}: {sorted(p.stem for p in RUNS_DIR.glob('*.json'))} exist")
    return json.loads(path.read_text())


def stored_run_ids() -> list[str]:
    return sorted(p.stem for p in RUNS_DIR.glob("*.json"))
