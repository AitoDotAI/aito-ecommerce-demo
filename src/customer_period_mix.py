"""What a period changed when no segment is ticked (ADR 0060): what customers bought, and which segments moved, against the period before.

With a segment ticked the Preferences and Other segments tabs compare it with the customers outside it. With only a period there is no
outside, so the comparison is the period before it, of the same length (ADR 0055). The same customers are in both timeframes' context: those
who ordered in either. For each category and brand, its share of the units they bought in the period against its share before it; for
each segment, the change in what its customers spent, each customer against themselves (the `revenue_eur` figure of `customer_period`).
"""

from __future__ import annotations

from math import sqrt
from statistics import mean, variance

from src.customer_period import MEAN_Z, UNBOUNDED_Z, _total, compare, previous_period

MIN_UNITS = 20           # an item bought fewer times than this in the two timeframes together is not worth a row
KINDS = (("Category", "category"), ("Brand", "brand"))
SPAN = lambda months, first, last: set(months[months.index(first):months.index(last) + 1])


def preference_changes(rows: dict[str, dict], products: dict[str, dict], ids: list[str], months: list[str], start: str, end: str,
                       min_units: int = MIN_UNITS) -> list[dict]:
    """Categories and brands the customers `ids` bought, as their share of the units bought in the period against their share before it.

    A share of what was bought, so it sums to 100 % in each timeframe and the change is in the mix: when more customers order in the period
    every item rises, and a share of customers would show only that. `rows` and `products` are the stored rows (`customer_rows`): a customer's
    `lines` are [sku, month, qty, returned, paid]; a returned line is not something bought. The margin treats the units as independent, which
    is narrower than the truth (one customer buys several units): read it as a floor."""
    before = previous_period(months, start, end)
    this, previous = SPAN(months, start, end), SPAN(months, *before)
    units: dict[str, dict[str, list[int]]] = {field: {} for _, field in KINDS}
    totals = [0, 0]
    for cid in ids:
        for sku, month, qty, returned, _paid in rows[cid]["lines"]:
            if returned or month not in this | previous:
                continue
            slot = 0 if month in this else 1
            totals[slot] += qty
            for _, field in KINDS:
                units[field].setdefault(products[sku][field], [0, 0])[slot] += qty
    if not all(totals):
        return []
    out = []
    for title, field in KINDS:
        for item, (n_now, n_then) in sorted(units[field].items()):
            if n_now + n_then < min_units:
                continue
            p_now, p_then = n_now / totals[0], n_then / totals[1]
            margin = MEAN_Z * sqrt(p_now * (1 - p_now) / totals[0] + p_then * (1 - p_then) / totals[1])
            out.append({"kind": title, "label": item, "points": round(100 * (p_now - p_then), 1), "margin_points": round(100 * margin, 1),
                        "clear": abs(p_now - p_then) > margin, "share": round(p_now, 3), "share_others": round(p_then, 3), "units": totals[0]})
    return sorted(out, key=lambda r: (not r["clear"], -abs(r["points"])))


def segment_changes(customers: dict[str, dict], months: list[str], start: str, end: str, conditions: list[str], min_customers: int) -> list[dict]:
    """For each segment `trait:value` with at least `min_customers` customers: what each spent in the period against the period before, and
    whether that change differs from the change of the customers outside it.

    When the whole shop grows every segment does, so the change alone only ranks segments by size. What stands out is a segment that moved
    more or less than the others: the mean of its customers' changes against the mean of the others', as a Welch z (each group's own spread)."""
    before = previous_period(months, start, end)
    this, previous = SPAN(months, start, end), SPAN(months, *before)
    context = {cid: c for cid, c in customers.items() if any(m in c["months"] for m in this | previous)}
    change = {cid: _total(c, this, 1) - _total(c, previous, 1) for cid, c in context.items()}
    out = []
    for condition in conditions:
        trait, value = condition.split(":", 1)
        inside = [cid for cid, c in context.items() if _meets(c, trait, value)]
        outside = [cid for cid in context if cid not in set(inside)]
        if len(inside) < min_customers or len(outside) < min_customers:
            continue
        own = compare([customers[cid] for cid in inside], months, start, end)["figures"]["revenue_eur"]
        gap = mean(change[cid] for cid in inside) - mean(change[cid] for cid in outside)
        spread = sqrt(variance(change[cid] for cid in inside) / len(inside) + variance(change[cid] for cid in outside) / len(outside))
        z = round(abs(gap) / spread, 2) if spread else (UNBOUNDED_Z if gap else 0.0)
        out.append({"trait": trait, "value": value, "customers": len(inside), "this": own["this"], "previous": own["previous"], "change": own["change"],
                    "gap_eur": round(gap, 2), "z": z, "clear": z > MEAN_Z})
    return sorted(out, key=lambda r: (not r["clear"], -r["z"]))


def _meets(customer: dict, trait: str, value: str) -> bool:
    from src.customer_selection import meets

    return meets(customer, trait, value)
