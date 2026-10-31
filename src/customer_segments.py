"""Segments of customers by trait, and how each segment responds to the shop's actions (ADR 0053).

Both are counts over the release's rows, with the number of rows beside every figure:

  - `segments`: for each trait value, how many profiled customers, their churn rate, spend and revenue (their
    orders' total, lifetime and the last 12 months, and the share of the profiled customers' revenue; pets and diets overlap,
    so those shares do not add up to 1).
  - `response`: from the action table, the share who ordered within 30 days after each action,
    per segment, and the difference to doing nothing in the same segment.

A response cell with fewer than `THIN_BELOW` rows is flagged thin and has no lift: a difference of two
small rates is noise. A lift carries its 95 % margin, and is `clear` only when it is larger than that. These are observed rates, not a model's predictions; Aito's per-customer predictions
(Shopkeeper) are fitted to the same rows.
"""

from __future__ import annotations

from collections import defaultdict
from math import sqrt

from src.customer_traits import NOT_PROFILED, TOO_FEW

THIN_BELOW = 30
TRAITS = ("offer", "price", "rating", "pets")
# The columns of the action table that describe the customer's situation, as the shopkeeper agent reads them.
RESPONSE_FIELDS = ("offer_buyer", "recency_bucket", "email_history", "tracking_consent", "spend_band", "open_issue")
ACTIONS = ("email", "ad", "discount", "voucher", "apology")


def segments(traits: list[dict], customers: dict[str, dict]) -> dict:
    profiled = [t for t in traits if t["profiled"]]
    revenue = sum(customers[t["customer_id"]]["revenue_eur"] for t in profiled) or 1.0
    out = {"customers": len(traits), "profiled": len(profiled), "not_profiled": len(traits) - len(profiled),
           "profiled_revenue_eur": round(revenue, 2), "by_trait": {}}
    for trait in TRAITS:
        groups = defaultdict(list)
        for t in profiled:
            for value in (t["pets"] if trait == "pets" else [t[trait]]):
                groups[value].append(customers[t["customer_id"]])
        out["by_trait"][trait] = [_segment(value, rows, len(profiled), revenue) for value, rows in sorted(groups.items())
                                  if value not in (NOT_PROFILED, TOO_FEW)] + (
            [{"value": TOO_FEW, **_count(groups[TOO_FEW], len(profiled)),
               "revenue_eur": round(sum(r["revenue_eur"] for r in groups[TOO_FEW]), 2),
               "revenue_share": round(sum(r["revenue_eur"] for r in groups[TOO_FEW]) / revenue, 3)}] if TOO_FEW in groups else [])
    diets = defaultdict(list)
    for t in profiled:
        for tag in t["diets"]:
            diets[tag].append(customers[t["customer_id"]])
    out["by_trait"]["diets"] = [_segment(tag, rows, len(profiled), revenue) for tag, rows in sorted(diets.items(), key=lambda kv: -len(kv[1]))]
    return out


def _count(rows: list[dict], profiled: int) -> dict:
    return {"customers": len(rows), "share": round(len(rows) / profiled, 3)}


def _segment(value: str, rows: list[dict], profiled: int, profiled_revenue: float) -> dict:
    return {"value": value, **_count(rows, profiled),
            "churn_rate": round(sum(r["churned"] for r in rows) / len(rows), 3),
            "avg_spend_eur": round(sum(r["total_spent_eur"] for r in rows) / len(rows), 2),
            "revenue_eur": round(sum(r["revenue_eur"] for r in rows), 2),
            "revenue_12m_eur": round(sum(r["revenue_12m_eur"] for r in rows), 2),
            "revenue_share": round(sum(r["revenue_eur"] for r in rows) / profiled_revenue, 3),
            "thin": len(rows) < THIN_BELOW}


def response(actions: list[dict]) -> dict:
    """For each field and value, each action's order rate and its lift over no action in that segment."""
    out = {}
    for field in RESPONSE_FIELDS:
        cells = defaultdict(lambda: [0, 0])          # (value, action) -> [rows, ordered]
        for row in actions:
            cell = cells[(row[field], row["action"])]
            cell[0] += 1
            cell[1] += bool(row["purchased_30d"])
        out[field] = []
        for value in sorted({v for v, _ in cells}):
            none_rows, none_ordered = cells[(value, "none")]
            entry = {"value": value, "none": {"rows": none_rows, "order_rate": _rate(none_ordered, none_rows)}, "actions": {}}
            for action in ACTIONS:
                rows, ordered = cells[(value, action)]
                thin = rows < THIN_BELOW or none_rows < THIN_BELOW
                lift, margin = (None, None) if thin else _lift(ordered, rows, none_ordered, none_rows)
                entry["actions"][action] = {"rows": rows, "order_rate": _rate(ordered, rows), "thin": thin,
                                            "lift_points": lift, "margin_points": margin,
                                            "clear": None if thin else abs(lift) > margin}
            out[field].append(entry)
    return out


def _rate(ordered: int, rows: int) -> float | None:
    return round(ordered / rows, 3) if rows else None


def _lift(ordered: int, rows: int, none_ordered: int, none_rows: int) -> tuple[float, float]:
    """The difference in order rate in points, and its 95 % margin (normal approximation for two rates)."""
    p, q = ordered / rows, none_ordered / none_rows
    return round((p - q) * 100, 1), round(1.96 * sqrt(p * (1 - p) / rows + q * (1 - q) / none_rows) * 100, 1)
