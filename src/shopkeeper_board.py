"""The Board: the shop's list of systematic improvements, raised by the agent's runs (ADR 0052).

A finding is about the configuration (which actions, in which situations, how much needs a person),
not about one customer. Each says what it rests on, so a person can check it. The agent proposes;
it changes nothing. Nothing here claims that acting on a finding improves results: that waits for a
measured change.
"""

from __future__ import annotations

from collections import Counter

from src.shopkeeper_gate import NEVER_AUTO, QUIET, GateSettings
from src.shopkeeper_run import decide_steps


def board_for(run: dict, settings: GateSettings) -> list[dict]:
    decided = decide_steps(run, settings)
    items = [*_thin_evidence(run, decided, settings), *_approval_load(run, decided), *_root_causes(run)]
    return [{"id": f"{run['id']}-{i + 1}", "status": "open", "raised_by": run["id"], **item} for i, item in enumerate(items)]


def _thin_evidence(run: dict, decided: list[dict], settings: GateSettings) -> list[dict]:
    thin = [s for s in decided if s["outcome"] == QUIET and s["rows"] < settings.min_rows and s["best"]["action"] != "none"]
    if not thin:
        return []
    by_action = Counter(s["best"]["label"] for s in thin)
    return [{
        "kind": "evidence", "owner": "shopkeeper",
        "title": f"{len(thin)} of {len(decided)} best actions have fewer than {settings.min_rows} past rows matching their exact situation",
        "detail": ("The agent stayed quiet on these: " + ", ".join(f"{label} ({n})" for label, n in by_action.most_common())
                   + ". Trying those actions on more customers in the same situations would give the next run something to act on."),
        "evidence": [f"{s['name']}: {s['best']['label']}, {s['rows']} rows" for s in thin],
    }]


def _approval_load(run: dict, decided: list[dict]) -> list[dict]:
    queued = [s for s in decided if s["outcome"] == NEVER_AUTO]
    if not queued:
        return []
    net = sum(s["best"]["net_vs_none_eur"] for s in queued)
    total = sum(s["best"]["net_vs_none_eur"] for s in decided if s["outcome"] != QUIET)
    kinds = Counter(s["best"]["label"] for s in queued)
    return [{
        "kind": "approval", "owner": "shopkeeper",
        "title": f"{len(queued)} of {len(decided)} proposals need a person, holding {net:.0f} € of {total:.0f} € expected",
        "detail": ("Kinds the store always sends through a person: " + ", ".join(f"{label} ({n})" for label, n in kinds.most_common())
                   + ". If the shop trusts one of these kinds, taking it off the list lets the agent act on it; the list is a setting."),
        "evidence": [f"{s['name']}: {s['best']['label']}, +{s['best']['net_vs_none_eur']:.2f} € expected" for s in queued],
    }]


def _root_causes(run: dict) -> list[dict]:
    causes = []
    for tell in run["root_causes"]["tells"]:
        causes.append({
            "kind": "root_cause", "owner": "agent",
            "title": f"{tell['label']}: {tell['lift']:.1f}× the churn",
            "detail": (f"{tell['churn_rate'] * 100:.1f} % of customer-months with this churned, against "
                       f"{tell['churn_rate_without'] * 100:.1f} % without, from {tell['customer_months']} customer-months. "
                       f"{tell['at_risk_listed']} of the {len(run['steps'])} customers in this run have it."),
            "evidence": [f"_relate-style rates from the Retention snapshot, as of {run['as_of_month']}"],
        })
    for driver in run["root_causes"]["drivers"]:
        causes.append({
            "kind": "root_cause", "owner": "agent",
            "title": f"{driver['field'].capitalize()} {driver['value']}: {driver['lift']:.1f}× the churn",
            "detail": (f"{driver['churn_rate'] * 100:.1f} % of {driver['customers']} such customers churned, against "
                       f"{driver['churn_rate_overall'] * 100:.1f} % overall."),
            "evidence": [f"_relate on churned, from the Retention snapshot, as of {run['as_of_month']}"],
        })
    return causes
