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
from src.customer_feedback import MIN_RESPONDENTS, feedback_by_segment
from src.customer_preference_ranking import label, ranking
from src.customer_relations import MIN_GROUP, memberships, selection_preferences, selection_relations
from src.customer_segments import TRAITS, response, segment_stats

SINGLE_VALUED = ("offer", "price", "rating", "margin", "status", "region")
FILTERS = ("region", "category", "brand", "review", "nps")    # where a customer lives and what they bought: they narrow a selection, they are not profiled traits
MULTI_VALUED = {"pets": "pets", "diets": "diets", "category": "categories", "brand": "brands", "review": "review_topics", "nps": "nps_groups"}   # condition trait -> the customer fact that lists the values
STAGES = ("impressions", "clicks", "carts", "purchases")
TREND_RECENT_MONTHS = 3
NPS_WINDOW_MONTHS = 6


def parse(conditions: list[str]) -> list[tuple[str, str]]:
    """The (trait, value) pairs, each valid and no single-valued trait twice."""
    parsed = []
    for condition in conditions:
        trait, sep, value = condition.partition(":")
        if not sep or not value or trait not in TRAITS + ("diets",) + FILTERS:
            raise ValueError(f"Not a condition: {condition!r} (expected trait:value, trait one of {', '.join(TRAITS + ('diets',) + FILTERS)})")
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
    return value in customer[MULTI_VALUED[trait]] if trait in MULTI_VALUED else customer[trait] == value


def members(customers: dict[str, dict], parsed: list[tuple[str, str]]) -> list[str]:
    return [cid for cid, c in customers.items() if all(meets(c, t, v) for t, v in parsed)]


def options(customers: dict[str, dict], parsed: list[tuple[str, str]]) -> dict[str, dict]:
    """For every condition the tree offers: the figures the selection would have if it were ticked (replacing the same trait's value).

    The customers who meet each condition are listed once, so every option is an intersection of those lists, not a new pass over everyone."""
    who: dict[tuple[str, str], set[str]] = defaultdict(set)
    for cid, c in customers.items():
        for trait in TRAITS + ("diets",) + FILTERS:
            for value in (c[MULTI_VALUED[trait]] if trait in MULTI_VALUED else [c[trait]]):
                if value not in ("too few purchases",):
                    who[(trait, value)].add(cid)
    out = {}
    for trait, value in sorted(who):
        kept = {(t, v) for t, v in parsed if t != trait or t not in SINGLE_VALUED} | {(trait, value)}
        ids = set.intersection(*(who.get(condition, set()) for condition in kept))
        out[f"{trait}:{value}"] = _tree_figures([c for cid, c in customers.items() if cid in ids])
    return out


def _tree_figures(rows: list[dict]) -> dict:
    """What the tree shows beside a condition, whichever figure is chosen: the size, purchases, revenue, profit per customer and NPS."""
    return {"customers": len(rows), "orders": sum(n for r in rows for n, _, _ in r["months"].values()),
            "revenue_eur": round(sum(r["net_revenue_eur"] for r in rows), 2),
            "profit_per_customer_eur": round(sum(r["profit_eur"] for r in rows) / len(rows), 2) if rows else None,
            "nps": _nps([group for r in rows for _, group in r["nps"]]),
            "churn_rate": round(sum(r["churned"] for r in rows) / len(rows), 3) if rows else None}


def _nps(groups: list[str]) -> float | None:
    if len(groups) < MIN_RESPONDENTS:
        return None
    return round(100 * (groups.count("promoter") - groups.count("detractor")) / len(groups), 1)


def view(facts: dict, parsed: list[tuple[str, str]], actions: list[dict], reviews: list[dict], answers: list[dict], summary: dict) -> dict:
    customers = facts["customers"]
    key = key_of(parsed)
    inside = set(members(customers, parsed))
    base = {"key": key, "conditions": [f"{t}:{v}" for t, v in parsed], "customers": len(inside), "options": options(customers, parsed)}
    if len(inside) < MIN_GROUP:
        return {**base, "too_small": True, "min_customers": MIN_GROUP}
    months = sorted({m for c in customers.values() for m in c["months"]})
    keys = ["all", key] if key != "all" else ["all"]
    segments_of = {cid: keys if cid in inside else ["all"] for cid in customers}
    rows = [customers[cid] for cid in inside]
    feedback = feedback_by_segment(reviews, answers, segments_of, [key])
    return {**base, "too_small": False,
            "segment": {**segment_stats("selection", key, rows, summary["profiled"], summary["profiled_revenue_eur"], summary["profiled_profit_eur"]),
                        "key": key},
            "funnel": {"selected": _funnel(rows), "all": _funnel(customers.values())},
            "relations": selection_relations({cid: memberships({**c, "profiled": True}) for cid, c in customers.items()}, inside,
                                             {t for t, _ in parsed if t in SINGLE_VALUED}),
            "preferences": _named(selection_preferences(inside, {cid: set(c["pets"]) for cid, c in customers.items()},
                                                        {cid: c["bought"] for cid, c in customers.items()}), facts["product_names"]),
            "acquisition": acquisition_by_segment({cid: c["first"] for cid, c in customers.items() if c["first"]}, segments_of,
                                                  {cid: c["profit_eur"] for cid, c in customers.items()}, [key]).get(key, {}),
            "response": response(actions, summary["gross_margin"], lambda row: segments_of.get(row["customer_id"], ())).get(key),
            "feedback": {"selected": feedback[key], "all": feedback["all"]},
            "trend": {"selected": _trend(rows, months), "all": _trend(customers.values(), months)}}


def ranking_for(facts: dict, parsed: list[tuple[str, str]], variable: str) -> dict:
    """Where the selection sits in the ranking of customers by one preference (a share of what they bought): offer, the cheaper half,
    better rated, a kind of pet, a category or a brand. The view opens it behind the "?" beside the segment."""
    if variable not in facts["shares"]:
        raise ValueError(f"No preference {variable!r} to rank by; the choices are {', '.join(sorted(facts['shares']))}")
    key = key_of(parsed)
    inside = set(members(facts["customers"], parsed))
    segments_of = {cid: ["all", key] if cid in inside and key != "all" else ["all"] for cid in facts["customers"]}
    return {"label": label(variable), "key": key, "segment_customers": len(inside),
            **ranking(facts["shares"][variable], segments_of, [key])}


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
    per_month: dict[str, list] = defaultdict(lambda: [0, 0, 0.0, 0.0])
    for r in rows:
        for month, (orders, revenue, gross) in r["months"].items():
            per_month[month][0] += 1
            per_month[month][1] += orders
            per_month[month][2] += revenue
            per_month[month][3] += gross
    out = {"months": months, "customers": [per_month[m][0] for m in months], "orders": [per_month[m][1] for m in months],
           "revenue_eur": [round(per_month[m][2], 2) for m in months],
           "profit_per_customer_eur": [round(per_month[m][3] / per_month[m][0], 2) if per_month[m][0] else 0.0 for m in months],
           "nps": _rolling_nps(rows, months), "churn_rate": _churn_rate(rows, months)}
    out["recent_vs_before"] = {kpi: _change(out[kpi]) for kpi in ("customers", "orders", "revenue_eur", "profit_per_customer_eur")}
    out["recent_vs_before"]["nps"] = _point_change(out["nps"])
    out["recent_vs_before"]["churn_rate"] = _point_change(out["churn_rate"])
    return out


def _rolling_nps(rows, months: list[str]) -> list[float | None]:
    """NPS of the answers given in the `NPS_WINDOW_MONTHS` months up to each month; None where there are too few answers to call a score."""
    answered = [(m, g) for r in rows for m, g in r["nps"]]
    out = []
    for i in range(len(months)):
        window = set(months[max(0, i - NPS_WINDOW_MONTHS + 1):i + 1])
        out.append(_nps([g for m, g in answered if m in window]))
    return out


def _month_number(month: str) -> int:
    year, number = month.split("-")
    return int(year) * 12 + int(number)


def _churn_rate(rows, months: list[str]) -> list[float | None]:
    """Per month, the share of the customers who had ordered by then that had not ordered in the three months up to it: the rule
    the churned flag follows at the end of the data (no order in the last three months), applied to every month."""
    ordered = [{_month_number(m) for m in r["months"]} for r in rows]
    out = []
    for month in months:
        now = _month_number(month)
        known = [o for o in ordered if o and min(o) <= now]
        lapsed = [o for o in known if not any(now - 2 <= m <= now for m in o)]
        out.append(round(len(lapsed) / len(known), 3) if known else None)
    return out


def _point_change(series: list[float | None]) -> float | None:
    """The figure now against `TREND_RECENT_MONTHS` months earlier, as a difference (None where either is missing)."""
    now, before = (series[-1], series[-1 - TREND_RECENT_MONTHS]) if len(series) > TREND_RECENT_MONTHS else (None, None)
    return round(now - before, 3) if now is not None and before is not None else None


def _change(series: list[float]) -> float | None:
    """The last `TREND_RECENT_MONTHS` months against the same number before them, as a fraction (None if there is no base)."""
    if len(series) < 2 * TREND_RECENT_MONTHS:
        return None
    recent, before = sum(series[-TREND_RECENT_MONTHS:]), sum(series[-2 * TREND_RECENT_MONTHS:-TREND_RECENT_MONTHS])
    return round(recent / before - 1, 3) if before else None
