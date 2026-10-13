"""One `_relate` hit as a lift with its counts and 95 % interval.

Shop analytics (ADR 0031) shows every finding as a row like "1–2 stars:
0.79×, 923 of 12,135 purchases, 95 % interval 0.74–0.84". This module
turns `_relate` hits into those rows and keeps only the ones whose
interval stays on one side of 1 (`is_real_lift`, the rule Price and
Demand already apply), so no noise is shown as a pattern.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from src.aito_client import AitoClient, AitoError
from src.aito_compat import related_value
from src.price_bands import is_real_lift, lift_interval


@dataclass(frozen=True)
class LiftRow:
    field: str             # "product_sku.rating_band"
    value: str             # "1-2"; a Boolean reads "true" / "false"
    lift: float            # share among the condition's rows / share among all rows
    interval_low: float    # 95 % interval on the lift
    interval_high: float
    rows_with_value: int   # fOnCondition: the condition's rows that have the value
    condition_rows: int    # fCondition: the condition's rows (e.g. all purchases)


def display_value(value: object) -> str:
    """A related value as text. Booleans read as JSON does, not as Python's
    `True`, because the page shows them."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def lift_row(field: str, value: object, lift: float, fs: dict) -> LiftRow | None:
    """The row for one lift, or None when its interval includes 1.

    `fs` holds the four counts `_relate` returns (`fOnCondition`,
    `fCondition`, `f`, `n`). Dropping a lift here is the documented rule,
    not a silent filter: the caller lists the fields that kept no row.
    """
    if not is_real_lift(lift, fs):
        return None
    low, high = lift_interval(lift, fs["fOnCondition"], fs["fCondition"], fs["f"], fs["n"])
    # Rounded outward, and checked again: an interval of 0.996 shown as
    # "0.93–1.00" would read as including 1.
    low, high = math.floor(low * 100) / 100, math.ceil(high * 100) / 100
    if low <= 1 <= high:
        return None
    return LiftRow(
        field=field,
        value=display_value(value),
        lift=round(lift, 2),
        interval_low=low,
        interval_high=high,
        rows_with_value=int(fs["fOnCondition"]),
        condition_rows=int(fs["fCondition"]),
    )


def relate_hits(client: AitoClient, body: dict) -> list[dict]:
    """Send one `_relate` body and return its hits, or raise.

    No hits, or a full page of them, both mean the view would show a
    wrong picture: the first that the field or condition doesn't exist in
    this data, the second that some values may have been cut off.
    """
    hits = client.relate(table=body["from"], where=body["where"],
                         relate_field=body["relate"], limit=body["limit"])["hits"]
    if not hits:
        raise AitoError(f"_relate returned no hits for {body}")
    if len(hits) >= body["limit"]:
        raise AitoError(f"_relate returned a full page of {body['limit']} hits for {body}; values may be cut off")
    return hits


def real_lift_rows(client: AitoClient, body: dict) -> list[LiftRow]:
    """The rows of one field-form `_relate` whose interval excludes 1."""
    field = body["relate"]
    rows = []
    for hit in relate_hits(client, body):
        row = lift_row(field, related_value(hit, field), float(hit["lift"]), hit["fs"])
        if row is not None:
            rows.append(row)
    return rows


def by_strength(rows: list) -> list:
    """Strongest first, in either direction: 0.5× is as strong as 2×."""
    return sorted(rows, key=lambda r: abs(math.log(r.lift)), reverse=True)
