"""Arrange the lifts of a `$why` for reading: groups as one row, strongest first.

Aito's `$why` lists a joint lift for several conditions that hold together (a `$group`
or `$and`), and, as separate factors, a small lift for each of those conditions on its
own: what remains of each after the joint is counted. Printed as they come, the Product
filling popover showed a joint card and then ten near-identical cards (×1.0 each) for
the words of one product name.

So a group becomes one row:
- its lift is the joint lift times the lifts of its members, so the product of all rows
  is unchanged and the popover's equation still multiplies out;
- the joint lift and each member stay in the row (`joint_lift`, `members`), so nothing
  is dropped;
- a single-condition lift belongs to the largest group that holds the same condition
  (same field, value and absence flag); one that no group holds stays its own row.

Rows, and members within a row, are ordered by how far their lift is from 1 either way
(|log lift|): a protective 0.5 outranks a 1.8. Ties keep Aito's order.
"""

from __future__ import annotations

import math


def arrange_lifts(lifts: list[dict]) -> list[dict]:
    """The popover's rows from the flat lifts `process_why` collected."""
    groups = [lift for lift in lifts if len(lift["propositions"]) > 1]
    members: dict[int, list[dict]] = {i: [] for i in range(len(groups))}
    rows: list[dict] = []

    for lift in lifts:
        if len(lift["propositions"]) > 1:
            continue
        owner = _largest_group_holding(groups, _condition(lift["propositions"][0]))
        if owner is None:
            rows.append(lift)
        else:
            members[owner].append(lift)

    for i, group in enumerate(groups):
        if not members[i]:
            rows.append(group)
            continue
        parts = _strongest_first(members[i])
        combined = group["lift"]
        for part in parts:
            combined *= part["lift"]
        rows.append({**group, "lift": round(combined, 3), "joint_lift": group["lift"], "members": parts})

    return _strongest_first(rows)


def _condition(proposition: dict) -> tuple[str, str, bool]:
    return proposition["field"], str(proposition["value"]), bool(proposition.get("negate"))


def _largest_group_holding(groups: list[dict], condition: tuple[str, str, bool]) -> int | None:
    holding = [i for i, group in enumerate(groups)
               if condition in {_condition(p) for p in group["propositions"]}]
    # Most conditions first; of equal size, the one Aito listed first.
    return max(holding, key=lambda i: (len(groups[i]["propositions"]), -i), default=None)


def _strongest_first(rows: list[dict]) -> list[dict]:
    # sorted() is stable, so equal strengths keep Aito's order.
    return sorted(rows, key=lambda row: -abs(math.log(max(row["lift"], 1e-9))))
