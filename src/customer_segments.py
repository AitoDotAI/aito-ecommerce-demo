"""Segments of customers by trait, and how each segment responds to the shop's actions (ADR 0053).

Both are counts over the release's rows, with the number of rows beside every figure:

  - `segments`: for each trait value, how many profiled customers, their churn rate, spend and revenue (their
    orders' total, lifetime and the last 12 months, and the share of the profiled customers' revenue; pets and diets overlap,
    so those shares do not add up to 1).
  - `response`: from the action table, the share who ordered within 30 days after each action, and what it earned,
    per segment (a row counts toward the segments of its customer), and the difference to doing nothing in the same segment.
    A customer's traits come from their whole history, so this describes the segments as they are now, not what was known
    when each action was sent.

A response cell with fewer than `THIN_BELOW` rows is flagged thin and has no lift: a difference of two
small rates is noise. A lift carries its 95 % margin, and is `clear` only when it is larger than that. These are observed rates, not a model's predictions; Aito's per-customer predictions
(Shopkeeper) are fitted to the same rows.
"""

from __future__ import annotations

from collections import defaultdict
from math import sqrt
from statistics import mean, variance

from src.customer_traits import NOT_PROFILED, TOO_FEW

THIN_BELOW = 30
TRAITS = ("offer", "price", "rating", "pets")
ACTIONS = ("email", "ad", "discount", "voucher", "apology")


def segments(traits: list[dict], customers: dict[str, dict]) -> dict:
    profiled = [t for t in traits if t["profiled"]]
    revenue = sum(customers[t["customer_id"]]["revenue_eur"] for t in profiled) or 1.0
    profit = sum(customers[t["customer_id"]]["profit_eur"] for t in profiled) or 1.0
    out = {"customers": len(traits), "profiled": len(profiled), "not_profiled": len(traits) - len(profiled),
           "profiled_revenue_eur": round(revenue, 2), "profiled_profit_eur": round(profit, 2), "by_trait": {}}
    for trait in TRAITS:
        groups = defaultdict(list)
        for t in profiled:
            for value in (t["pets"] if trait == "pets" else [t[trait]]):
                groups[value].append(customers[t["customer_id"]])
        out["by_trait"][trait] = [_segment(trait, value, rows, len(profiled), revenue, profit) for value, rows in sorted(groups.items())
                                  if value not in (NOT_PROFILED, TOO_FEW)] + (
            [{"key": f"{trait}:{TOO_FEW}", "value": TOO_FEW, **_count(groups[TOO_FEW], len(profiled)),
               "revenue_eur": round(sum(r["revenue_eur"] for r in groups[TOO_FEW]), 2),
               "revenue_share": round(sum(r["revenue_eur"] for r in groups[TOO_FEW]) / revenue, 3),
               "profit_eur": round(sum(r["profit_eur"] for r in groups[TOO_FEW]), 2),
               "profit_share": round(sum(r["profit_eur"] for r in groups[TOO_FEW]) / profit, 3)}] if TOO_FEW in groups else [])
    diets = defaultdict(list)
    for t in profiled:
        for tag in t["diets"]:
            diets[tag].append(customers[t["customer_id"]])
    out["by_trait"]["diets"] = [_segment("diets", tag, rows, len(profiled), revenue, profit) for tag, rows in sorted(diets.items(), key=lambda kv: -len(kv[1]))]
    return out


def _count(rows: list[dict], profiled: int) -> dict:
    return {"customers": len(rows), "share": round(len(rows) / profiled, 3)}


def _segment(trait: str, value: str, rows: list[dict], profiled: int, profiled_revenue: float, profiled_profit: float) -> dict:
    return {"key": f"{trait}:{value}", "value": value, **_count(rows, profiled),
            "churn_rate": round(sum(r["churned"] for r in rows) / len(rows), 3),
            "avg_spend_eur": round(sum(r["total_spent_eur"] for r in rows) / len(rows), 2),
            "revenue_eur": round(sum(r["revenue_eur"] for r in rows), 2),
            "revenue_12m_eur": round(sum(r["revenue_12m_eur"] for r in rows), 2),
            "revenue_share": round(sum(r["revenue_eur"] for r in rows) / profiled_revenue, 3),
            "profit_eur": round(sum(r["profit_eur"] for r in rows), 2),
            "profit_12m_eur": round(sum(r["gross_profit_12m_eur"] for r in rows), 2),
            "profit_per_customer_eur": round(sum(r["profit_eur"] for r in rows) / len(rows), 2),
            "margin": round(sum(r["gross_profit_eur"] for r in rows) / max(1e-9, sum(r["net_revenue_eur"] for r in rows)), 3),
            "profit_share": round(sum(r["profit_eur"] for r in rows) / profiled_profit, 3),
            "thin": len(rows) < THIN_BELOW}


def segment_keys(profile: dict) -> list[str]:
    """The segments a profiled customer is in, as "trait:value" (the key every segment is listed and looked up by)."""
    if not profile["profiled"]:
        return []
    keys = [f"{trait}:{profile[trait]}" for trait in ("offer", "price", "rating") if profile[trait] != TOO_FEW]
    return keys + [f"pets:{pet}" for pet in profile["pets"]] + [f"diets:{tag}" for tag in profile["diets"]]


def response(actions: list[dict], gross_margin: float, segments_of) -> dict:
    """For each segment, each action's order rate and its lift over no action in that segment, and what it earned.

    `segments_of(row)` gives the segment keys an action row counts toward (here: the segments of the row's customer).
    Earned is estimated: the 30-day spend at the shop's gross margin, less the action's cost, per customer-row."""
    cells = defaultdict(lambda: [0, 0])              # (segment, action) -> [rows, ordered]
    earned = defaultdict(list)                       # (segment, action) -> profit of each row
    for row in actions:
        for key in segments_of(row):
            cells[(key, row["action"])][0] += 1
            cells[(key, row["action"])][1] += bool(row["purchased_30d"])
            earned[(key, row["action"])].append(row["spend_30d_eur"] * gross_margin - row["cost_eur"])
    out = {}
    for key in sorted({k for k, _ in cells}):
        none_rows, none_ordered = cells[(key, "none")]
        entry = {"none": {"rows": none_rows, "order_rate": _rate(none_ordered, none_rows), "profit_eur": _mean(earned[(key, "none")])},
                 "actions": {}}
        for action in ACTIONS:
            rows, ordered = cells[(key, action)]
            thin = rows < THIN_BELOW or none_rows < THIN_BELOW
            lift, margin = (None, None) if thin else _lift(ordered, rows, none_ordered, none_rows)
            entry["actions"][action] = {"rows": rows, "order_rate": _rate(ordered, rows), "thin": thin,
                                        "lift_points": lift, "margin_points": margin,
                                        "clear": None if thin else abs(lift) > margin,
                                        "profit_eur": _mean(earned[(key, action)]),
                                        **_profit_lift(earned[(key, action)], earned[(key, "none")], thin)}
        out[key] = entry
    return out


def _rate(ordered: int, rows: int) -> float | None:
    return round(ordered / rows, 3) if rows else None


def _lift(ordered: int, rows: int, none_ordered: int, none_rows: int) -> tuple[float, float]:
    """The difference in order rate in points, and its 95 % margin (normal approximation for two rates)."""
    p, q = ordered / rows, none_ordered / none_rows
    return round((p - q) * 100, 1), round(1.96 * sqrt(p * (1 - p) / rows + q * (1 - q) / none_rows) * 100, 1)


def _mean(values: list[float]) -> float | None:
    return round(mean(values), 2) if values else None


def _profit_lift(action: list[float], none: list[float], thin: bool) -> dict:
    """The difference in profit per customer-row against no action, in euros, with its 95 % margin (two means)."""
    if thin:
        return {"profit_lift_eur": None, "profit_margin_eur": None, "profit_clear": None}
    lift = mean(action) - mean(none)
    margin = 1.96 * sqrt(variance(action) / len(action) + variance(none) / len(none))
    return {"profit_lift_eur": round(lift, 2), "profit_margin_eur": round(margin, 2), "profit_clear": abs(lift) > margin}
