"""A selection of conditions and everything the Customers view says about the customers who meet all of them (ADR 0053).

The tree lets the shop-keeper tick several conditions at once: premium-leaning AND dog owners AND high margin. A condition is
"trait:value". The shopping traits and margin take one value each; pets and diets can be ticked several times (a customer
buying for a dog and a cat meets both). The selection is counted from the stored facts (`customer_facts.py`) with the same
functions that profiled the single segments, so a selection of one condition says exactly what its segment did.

A selection with fewer than `MIN_GROUP` customers is given its size and nothing else: a rate over a handful of customers
is not a finding, and a list of what a handful bought describes them rather than a segment.
"""

from __future__ import annotations

from collections import defaultdict

from src.customer_acquisition import acquisition_by_segment
from src.customer_feedback import feedback_by_segment
from src.customer_preference_ranking import label, ranking
from src.customer_relations import MIN_GROUP, memberships, selection_preferences, selection_relations
from src.customer_segments import TRAITS, response, segment_stats

SINGLE_VALUED = ("offer", "price", "rating", "margin")
# The ranking each shopping condition is a slice of; margin, pets and diets are not a share of what a customer bought.
RANKED_BY = {"offer": "offer", "price": "cheaper", "rating": "rated"}
STAGES = ("impressions", "clicks", "carts", "purchases")
TREND_RECENT_MONTHS = 3


def parse(conditions: list[str]) -> list[tuple[str, str]]:
    """The (trait, value) pairs, each valid and no single-valued trait twice."""
    parsed = []
    for condition in conditions:
        trait, sep, value = condition.partition(":")
        if not sep or not value or trait not in TRAITS + ("diets",):
            raise ValueError(f"Not a condition: {condition!r} (expected trait:value, trait one of {', '.join(TRAITS + ('diets',))})")
        parsed.append((trait, value))
    singles = [t for t, _ in parsed if t in SINGLE_VALUED]
    if len(singles) != len(set(singles)):
        raise ValueError(f"A customer has one value of each of {', '.join(SINGLE_VALUED)}: {conditions!r} asks for two of one")
    if len(set(parsed)) != len(parsed):
        raise ValueError(f"The same condition twice: {conditions!r}")
    return sorted(parsed)


def key_of(parsed: list[tuple[str, str]]) -> str:
    return "+".join(f"{t}:{v}" for t, v in parsed) or "all"


def meets(customer: dict, trait: str, value: str) -> bool:
    return value in customer[trait] if trait in ("pets", "diets") else customer[trait] == value


def members(customers: dict[str, dict], parsed: list[tuple[str, str]]) -> list[str]:
    return [cid for cid, c in customers.items() if all(meets(c, t, v) for t, v in parsed)]


def options(customers: dict[str, dict], parsed: list[tuple[str, str]]) -> dict[str, int]:
    """For every condition the tree offers: how many customers there would be if it were ticked (replacing the same trait's value)."""
    values = sorted({(t, v) for c in customers.values() for t in TRAITS + ("diets",)
                     for v in (c[t] if t in ("pets", "diets") else [c[t]]) if v not in ("too few purchases",)})
    out = {}
    for trait, value in values:
        kept = [(t, v) for t, v in parsed if t != trait or t not in SINGLE_VALUED]
        out[f"{trait}:{value}"] = len(members(customers, sorted({*kept, (trait, value)})))
    return out


def view(facts: dict, parsed: list[tuple[str, str]], actions: list[dict], reviews: list[dict], answers: list[dict], summary: dict) -> dict:
    customers = facts["customers"]
    key = key_of(parsed)
    inside = set(members(customers, parsed))
    base = {"key": key, "conditions": [f"{t}:{v}" for t, v in parsed], "customers": len(inside), "options": options(customers, parsed)}
    if len(inside) < MIN_GROUP:
        return {**base, "too_small": True, "min_customers": MIN_GROUP}
    months = sorted({m for c in customers.values() for m in c["months"]})
    segments_of = {cid: ["all", key] if cid in inside else ["all"] for cid in customers}
    rows = [customers[cid] for cid in inside]
    return {**base, "too_small": False,
            "segment": {**segment_stats("selection", key, rows, summary["profiled"], summary["profiled_revenue_eur"], summary["profiled_profit_eur"]),
                        "key": key},
            "funnel": {"selected": _funnel(rows), "all": _funnel(customers.values())},
            "ranking": {RANKED_BY[t]: {"label": label(RANKED_BY[t]), **ranking(facts["shares"][RANKED_BY[t]], segments_of, [key])}
                        for t, _ in parsed if t in RANKED_BY},
            "relations": selection_relations({cid: memberships({**c, "profiled": True}) for cid, c in customers.items()}, inside,
                                             {t for t, _ in parsed if t in SINGLE_VALUED}),
            "preferences": _named(selection_preferences(inside, {cid: set(c["pets"]) for cid, c in customers.items()},
                                                        {cid: c["bought"] for cid, c in customers.items()}), facts["product_names"]),
            "acquisition": acquisition_by_segment({cid: c["first"] for cid, c in customers.items() if c["first"]}, segments_of,
                                                  {cid: c["profit_eur"] for cid, c in customers.items()}, [key]).get(key, {}),
            "response": response(actions, summary["gross_margin"], lambda row: segments_of.get(row["customer_id"], ())).get(key),
            "feedback": feedback_by_segment(reviews, answers, segments_of, [key])[key],
            "trend": {"selected": _trend(rows, months), "all": _trend(customers.values(), months)}}


def _named(preferences: dict[str, dict], names: dict[str, str]) -> dict[str, dict]:
    for entry in preferences.values():
        for row in entry["products"]:
            row["name"] = names[row["item"]]
    return preferences


def _funnel(rows) -> dict[str, int]:
    return {stage: sum(r["funnel"][i] for r in rows) for i, stage in enumerate(STAGES)}


def _trend(rows, months: list[str]) -> dict:
    """Per month of the shop's history, oldest first: customers who ordered, orders, and revenue (the price paid on the lines
    kept). A month the selection did not order in is a zero, not a gap, so the last months compare like with like."""
    per_month: dict[str, list] = defaultdict(lambda: [0, 0, 0.0])
    for r in rows:
        for month, (orders, revenue) in r["months"].items():
            per_month[month][0] += 1
            per_month[month][1] += orders
            per_month[month][2] += revenue
    out = {"months": months, "customers": [per_month[m][0] for m in months], "orders": [per_month[m][1] for m in months],
           "revenue_eur": [round(per_month[m][2], 2) for m in months]}
    out["recent_vs_before"] = {kpi: _change(out[kpi]) for kpi in ("customers", "orders", "revenue_eur")}
    return out


def _change(series: list[float]) -> float | None:
    """The last `TREND_RECENT_MONTHS` months against the same number before them, as a fraction (None if there is no base)."""
    if len(series) < 2 * TREND_RECENT_MONTHS:
        return None
    recent, before = sum(series[-TREND_RECENT_MONTHS:]), sum(series[-2 * TREND_RECENT_MONTHS:-TREND_RECENT_MONTHS])
    return round(recent / before - 1, 3) if before else None
