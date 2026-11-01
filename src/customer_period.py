"""A period of months set against the rest of the shop's history, for the selected customers and for everyone (ADR 0055).

The period is picked on the trend graph. Orders, revenue and active customers are compared as a monthly average inside the
period against the average outside it, so a short period and a long remainder compare fairly. Profit per active customer is
weighted by the customers active each month. NPS and churn are rolling figures: they are read in the last month of the period
and in the month before it, and differ in points. The data is monthly, so a period is whole months.
"""

from __future__ import annotations

import re

AVERAGED = ("customers", "orders", "revenue_eur")
POINT_FIGURES = ("nps", "churn_rate")


def period_comparison(selected: dict, everyone: dict, start: str, end: str) -> dict:
    """`selected` and `everyone` are trends (`customer_selection._trend`); `start` and `end` are months, `end` included."""
    months = selected["months"]
    for month in (start, end):
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month) or month not in months:
            raise ValueError(f"Not a month of the data in the period: {month!r}; the data runs {months[0]} to {months[-1]}")
    first, last = months.index(start), months.index(end)
    if first > last:
        raise ValueError(f"The period starts after it ends: {start} to {end}")
    inside = list(range(first, last + 1))
    outside = [i for i in range(len(months)) if i not in inside]
    if not outside:
        raise ValueError(f"The period {start} to {end} is the whole history: nothing outside it to compare with")
    return {"from": start, "to": end, "months": len(inside), "months_outside": len(outside),
            "selected": _compare(selected, inside, outside, first), "all": _compare(everyone, inside, outside, first)}


def _compare(trend: dict, inside: list[int], outside: list[int], first: int) -> dict:
    out = {kpi: _averaged(trend[kpi], inside, outside) for kpi in AVERAGED}
    out["profit_per_customer_eur"] = _weighted(trend, inside, outside)
    for kpi in POINT_FIGURES:
        now, before = trend[kpi][inside[-1]], (trend[kpi][first - 1] if first > 0 else None)
        out[kpi] = {"inside": now, "outside": before, "change": round(now - before, 3) if now is not None and before is not None else None}
    return out


def _averaged(series: list[float], inside: list[int], outside: list[int]) -> dict:
    inner, outer = _mean([series[i] for i in inside]), _mean([series[i] for i in outside])
    return {"inside": inner, "outside": outer, "change": round(inner / outer - 1, 3) if outer else None}


def _weighted(trend: dict, inside: list[int], outside: list[int]) -> dict:
    def level(indices: list[int]) -> float:
        customers = sum(trend["customers"][i] for i in indices)
        return round(sum(trend["profit_per_customer_eur"][i] * trend["customers"][i] for i in indices) / customers, 2) if customers else 0.0
    inner, outer = level(inside), level(outside)
    return {"inside": inner, "outside": outer, "change": round(inner / outer - 1, 3) if outer else None}


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 2)
