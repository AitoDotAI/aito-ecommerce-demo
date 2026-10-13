"""Which `_relate` lifts to show, and with what interval.

Shop analytics (ADR 0031) shows a finding as a row like "1–2 stars:
0.79×, 923 of 12,135 purchases, interval 0.70–0.89". Three rules decide
which lifts become rows:

1. **Clustering.** Rows of one customer are not independent, so every
   count is divided by the section's design effect before it is used
   (`src/design_effect.py`). This widens the interval by √deff.
2. **Support.** A lift is tested only if it rests on at least 30
   independent purchases (or lines, or orders) after that division.
3. **Many tests at once.** A section tests dozens of lifts. Each interval
   is at the Bonferroni level for the number tested, so the chance that
   *any* shown row is a lift of exactly 1 is at most 5 % per section
   (assuming the design effect is right). It does not say each lift's
   size is exact, and a lift that isn't shown may still be real.

The interval is rounded outward to two decimals, so a top of 0.996 shows
as 1.00 and the row is left out rather than read as touching 1.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist

from src.aito_client import AitoClient, AitoError
from src.aito_compat import related_value
from src.price_bands import MIN_SWEET_SPOT_SUPPORT, lift_interval

FAMILY_CONFIDENCE = 0.95


@dataclass(frozen=True)
class Candidate:
    """One `_relate` hit before testing."""
    field: str
    value: str
    lift: float
    fs: dict               # fOnCondition, fCondition, f, n
    design_effect: float


@dataclass(frozen=True)
class LiftRow:
    field: str             # "product_sku.rating_band"
    value: str             # "1-2"; a Boolean reads "true" / "false"
    lift: float            # share among the condition's rows / share among all rows
    interval_low: float    # family-wise interval, widened for clustering
    interval_high: float
    rows_with_value: int   # fOnCondition: the condition's rows that have the value
    condition_rows: int    # fCondition: the condition's rows (e.g. all purchases)


@dataclass(frozen=True)
class Significance:
    tested: int            # lifts with enough independent support
    z: float               # two-sided Bonferroni z for `tested` tests
    family_confidence: float


def display_value(value: object) -> str:
    """A related value as text. Booleans read as JSON does, not as Python's
    `True`, because the page shows them."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def bonferroni_z(tests: int) -> float:
    if tests <= 0:
        return 0.0
    return NormalDist().inv_cdf(1 - (1 - FAMILY_CONFIDENCE) / (2 * tests))


def is_testable(candidate: Candidate) -> bool:
    return candidate.fs["fOnCondition"] / candidate.design_effect >= MIN_SWEET_SPOT_SUPPORT


def judge(candidates: list[Candidate]) -> tuple[list[LiftRow], Significance]:
    """The rows whose family-wise interval excludes 1, strongest first."""
    testable = [c for c in candidates if is_testable(c)]
    z = bonferroni_z(len(testable))
    rows = [row for row in (_row(c, z) for c in testable) if row is not None]
    return by_strength(rows), Significance(len(testable), round(z, 2), FAMILY_CONFIDENCE)


def _row(c: Candidate, z: float) -> LiftRow | None:
    effective = {k: c.fs[k] / c.design_effect for k in ("fOnCondition", "fCondition", "f", "n")}
    low, high = lift_interval(c.lift, effective["fOnCondition"], effective["fCondition"],
                              effective["f"], effective["n"], z=z)
    low, high = math.floor(low * 100) / 100, math.ceil(high * 100) / 100
    if low <= 1 <= high:
        return None
    return LiftRow(
        field=c.field, value=c.value, lift=round(c.lift, 2),
        interval_low=low, interval_high=high,
        rows_with_value=int(c.fs["fOnCondition"]), condition_rows=int(c.fs["fCondition"]),
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


def candidates_from_hits(field: str, hits: list[dict], design_effect: float) -> list[Candidate]:
    return [Candidate(field, display_value(related_value(h, field)), float(h["lift"]), h["fs"], design_effect)
            for h in hits]


def fields_without_clear_effect(fields: list[str], rows: list[LiftRow]) -> list[str]:
    shown = {r.field for r in rows}
    return [f for f in fields if f not in shown]


def by_strength(rows: list) -> list:
    """Strongest first, in either direction: 0.5× is as strong as 2×."""
    return sorted(rows, key=lambda r: abs(math.log(r.lift)), reverse=True)
