"""Where a segment's customers came from: channel, landing page, landing category (ADR 0053).

Each profiled customer has a first session, found through their visitor id: its source (the channel), its landing page
type and its landing category (none when they landed on the home page). For each segment and each of those, the
segment's share of customers against everyone else's, in points with a 99.7 % margin (many values are compared), and what
the customers of the segment who came that way earned per customer, with the same for everyone who came that way.

This reads only what was known when the customer arrived. It does not read whether they went on to become regulars: that
label carries the future, and only the Acquisition view may count it (tests/test_leakage_guards.py).
"""

from __future__ import annotations

from collections import Counter

from src.customer_relations import MIN_BUYERS, MIN_GROUP, share_difference
from src.customer_segments import THIN_BELOW, bootstrap_mean_interval

DIMENSIONS = ("source", "landing", "landing_category")
NO_CATEGORY = "home page (no category)"


def first_sessions(customers: list[dict], contexts: list[dict]) -> dict[str, dict[str, str]]:
    """customer_id -> the source, landing and landing category of the visitor's earliest session."""
    earliest: dict[str, dict] = {}
    for context in contexts:
        visitor = context["visitor"]
        if visitor not in earliest or (context["month"], context["context_id"]) < (earliest[visitor]["month"], earliest[visitor]["context_id"]):
            earliest[visitor] = context
    out = {}
    for customer in customers:
        first = earliest.get(customer["visitor"])
        if first is not None:
            out[customer["customer_id"]] = {"source": first["source"], "landing": first["landing"],
                                            "landing_category": first.get("landing_category") or NO_CATEGORY}
    return out


def acquisition_by_segment(first: dict[str, dict[str, str]], segments_of: dict[str, list[str]], profit: dict[str, float],
                           segment_keys: list[str]) -> dict[str, dict[str, list[dict]]]:
    """segment key (and "all") -> dimension -> a row per value, the biggest first."""
    known = [c for c in first if segments_of.get(c)]
    out: dict[str, dict[str, list[dict]]] = {}
    for key in ["all", *segment_keys]:
        inside = [c for c in known if key in segments_of[c]]
        outside = [c for c in known if key not in segments_of[c]]
        if len(inside) < MIN_GROUP:
            continue
        out[key] = {}
        for dim in DIMENSIONS:
            counts_in = Counter(first[c][dim] for c in inside)
            counts_out = Counter(first[c][dim] for c in outside)
            rows = []
            for value, n in counts_in.most_common():
                if n < MIN_BUYERS:
                    continue
                row = {"value": value, "customers": n, "share": round(n / len(inside), 3),
                       "profit_per_customer_eur": _mean([profit.get(c, 0.0) for c in inside if first[c][dim] == value]),
                       "profit_per_customer_ci": bootstrap_mean_interval([profit.get(c, 0.0) for c in inside if first[c][dim] == value]),
                       "profit_per_customer_all_eur": _mean([profit.get(c, 0.0) for c in known if first[c][dim] == value])}
                if outside:
                    points, margin = share_difference(n, len(inside), counts_out[value], len(outside))
                    row |= {"share_others": round(counts_out[value] / len(outside), 3), "points": points, "margin_points": margin,
                            "clear": abs(points) > margin}
                rows.append(row)
            out[key][dim] = rows
    return out


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if len(values) >= THIN_BELOW else None
