"""A period set against the one just before it, of the same length (ADR 0055).

The period is picked on the trend graph. What it is compared with is the timeframe immediately before it and as long as it:
a week against the week before, three months against the three before. The two timeframes are one statistical context: the
customers who ordered in either of them. Orders, revenue and gross profit are compared per customer of that context, each
customer against themselves, so the interval is that of the mean of the changes. NPS is read from the answers given in each
timeframe, and churn as the share of the customers who had ordered by then that had not in the three months up to the end of it.
The data is monthly, so a timeframe is whole months. A period with no room for a previous one is refused, not shortened.
"""

from __future__ import annotations

import re
from math import sqrt
from statistics import mean, stdev

from src.customer_feedback import MIN_RESPONDENTS
from src.customer_relations import share_difference

MEAN_Z = 1.96                      # 95 % for a mean of per-customer changes and for NPS
UNBOUNDED_Z = 99.0                 # a change with no spread around it, stated as a number JSON can carry
SHARE_Z = 3.0                      # the 99.7 % `share_difference` uses for churn
LAPSE_MONTHS = 3                   # churned: no order in the three months up to the end of the timeframe
PER_CUSTOMER = {"orders": 0, "revenue_eur": 1, "profit_per_customer_eur": 2}      # index into a customer's [orders, revenue, gross profit]


class NoPreviousPeriod(ValueError):
    """The period starts too early to have a previous one of the same length."""


def previous_period(months: list[str], start: str, end: str) -> tuple[str, str]:
    for month in (start, end):
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month) or month not in months:
            raise ValueError(f"Not a month of the data in the period: {month!r}; the data runs {months[0]} to {months[-1]}")
    first, last = months.index(start), months.index(end)
    if first > last:
        raise ValueError(f"The period starts after it ends: {start} to {end}")
    length = last - first + 1
    if first - length < 0:
        raise NoPreviousPeriod(f"No previous period of {length} month{'s' if length > 1 else ''}: {start} to {end} is preceded by only {first} "
                               f"month{'s' if first != 1 else ''} of data (it starts {months[0]})")
    return months[first - length], months[first - 1]


def compare(rows: list[dict], months: list[str], start: str, end: str) -> dict:
    """The period `start`..`end` against the one before it, for the customers `rows` (each with `months` and `nps`, as in the stored facts)."""
    before = previous_period(months, start, end)
    this = set(months[months.index(start):months.index(end) + 1])
    previous = set(months[months.index(before[0]):months.index(before[1]) + 1])
    context = [r for r in rows if any(m in r["months"] for m in this | previous)]
    figures = {"customers": _count(context, this, previous)}
    for kpi, index in PER_CUSTOMER.items():
        figures[kpi] = _per_customer(context, this, previous, index)
    figures["nps"] = _nps(context, this, previous)
    figures["churn_rate"] = _churn(rows, end, before[1], months)
    return {"from": start, "to": end, "months": len(this), "previous": {"from": before[0], "to": before[1]},
            "context_customers": len(context), "figures": figures}


def _standard_errors(difference: float, margin: float, margin_z: float) -> float | None:
    """How many standard errors the difference is: its margin is `margin_z` of them (1.96 for a mean at 95 %, 3 for a share at 99.7 %)."""
    if margin == float("inf"):
        return None
    if margin == 0:
        return UNBOUNDED_Z if difference else 0.0       # every customer moved the same way: no spread at all
    return round(margin_z * abs(difference) / margin, 2)


def _total(row: dict, within: set[str], index: int) -> float:
    return sum(v[index] for m, v in row["months"].items() if m in within)


def _count(context: list[dict], this: set[str], previous: set[str]) -> dict:
    now, before = (sum(any(m in r["months"] for m in span) for r in context) for span in (this, previous))
    return {"this": now, "previous": before, "change": round(now / before - 1, 3) if before else None, "margin": None, "clear": None, "z": None}


def _per_customer(context: list[dict], this: set[str], previous: set[str], index: int) -> dict:
    now = [_total(r, this, index) for r in context]
    before = [_total(r, previous, index) for r in context]
    mean_now, mean_before = mean(now), mean(before)
    differences = [a - b for a, b in zip(now, before)]
    margin = MEAN_Z * stdev(differences) / sqrt(len(differences)) if len(differences) > 1 else float("inf")
    return {"this": round(mean_now, 2), "previous": round(mean_before, 2),
            "change": round(mean_now / mean_before - 1, 3) if mean_before else None,
            "margin": round(margin / mean_before, 3) if mean_before else None, "clear": abs(mean_now - mean_before) > margin,
            "z": _standard_errors(mean_now - mean_before, margin, MEAN_Z)}


def _nps(context: list[dict], this: set[str], previous: set[str]) -> dict:
    now, before = (_answers(context, span) for span in (this, previous))
    if len(now) < MIN_RESPONDENTS or len(before) < MIN_RESPONDENTS:
        return {"this": None, "previous": None, "change": None, "margin": None, "clear": None, "z": None}
    score = lambda groups: 100 * (groups.count("promoter") - groups.count("detractor")) / len(groups)
    spread = lambda groups: 100 * sqrt(max(0.0, (groups.count("promoter") + groups.count("detractor")) / len(groups)
                                           - ((groups.count("promoter") - groups.count("detractor")) / len(groups)) ** 2) / len(groups))
    margin = MEAN_Z * sqrt(spread(now) ** 2 + spread(before) ** 2)
    return {"this": round(score(now), 1), "previous": round(score(before), 1), "change": round(score(now) - score(before), 1),
            "margin": round(margin, 1), "clear": abs(score(now) - score(before)) > margin,
            "z": _standard_errors(score(now) - score(before), margin, MEAN_Z)}


def _answers(context: list[dict], within: set[str]) -> list[str]:
    return [group for r in context for month, group in r["nps"] if month in within]


def _month_number(month: str) -> int:
    year, number = month.split("-")
    return int(year) * 12 + int(number)


def _lapsed(rows: list[dict], month: str) -> tuple[int, int]:
    """(customers who had ordered by `month` and not in the three months up to it, customers who had ordered by then)."""
    now = _month_number(month)
    ordered = [{_month_number(m) for m in r["months"]} for r in rows]
    known = [o for o in ordered if o and min(o) <= now]
    return sum(not any(now - LAPSE_MONTHS + 1 <= m <= now for m in o) for o in known), len(known)


def _churn(rows: list[dict], end: str, before_end: str, months: list[str]) -> dict:
    lapsed_now, known_now = _lapsed(rows, end)
    lapsed_before, known_before = _lapsed(rows, before_end)
    if not known_now or not known_before:
        return {"this": None, "previous": None, "change": None, "margin": None, "clear": None, "z": None}
    points, margin = share_difference(lapsed_now, known_now, lapsed_before, known_before)
    return {"this": round(lapsed_now / known_now, 3), "previous": round(lapsed_before / known_before, 3),
            "change": round(points / 100, 3), "margin": round(margin / 100, 3), "clear": abs(points) > margin,
            "z": _standard_errors(points, margin, SHARE_Z)}
