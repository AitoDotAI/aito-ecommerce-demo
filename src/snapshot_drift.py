"""Does a shipped snapshot still say what the live data says?

The precompute snapshots (`data/precomputed/`) and the committed evidence file
(`data/evidence/model-checks.json`) are claims about a database that keeps moving. Each is
reduced here to a few headline numbers, so a fresh run can be compared with what was shipped.
`./do aito-check` does the comparing (tests/test_aito_check.py); a difference fails it.
"""

from __future__ import annotations

from dataclasses import dataclass

ACCURACY_TOLERANCE = 0.02   # `_evaluate` samples a fixed seed, so a rerun agrees to within a case or two
EUROS_TOLERANCE = 0.005     # relative


@dataclass(frozen=True)
class Headline:
    """One number a snapshot claims, and how far a fresh run may differ from it."""

    value: float
    tolerance: float


@dataclass(frozen=True)
class Drift:
    name: str
    shipped: float
    live: float


def drifts(shipped: dict[str, Headline], live: dict[str, Headline]) -> list[Drift]:
    """The numbers where the live run differs from the shipped one by more than the tolerance.

    A number the live run does not have is an error, not a pass: a check that quietly skips what
    it cannot find would stay green after the thing it guards was renamed away."""
    missing = sorted(set(shipped) - set(live))
    assert not missing, f"the live run has no {missing}; the shipped snapshot claims them"
    return [Drift(name, claim.value, live[name].value) for name, claim in shipped.items()
            if abs(claim.value - live[name].value) > claim.tolerance]


def _count(value: float) -> Headline:
    return Headline(value, tolerance=0)


def _euros(value: float) -> Headline:
    return Headline(value, tolerance=value * EUROS_TOLERANCE)


def _accuracy(value: float) -> Headline:
    return Headline(value, tolerance=ACCURACY_TOLERANCE)


def headline_numbers(view: str, data: dict) -> dict[str, Headline]:
    """The numbers a snapshot of `view` is judged by. `data` is the snapshot's payload."""
    if view == "overview":
        k = data["kpis"]
        return {"orders": _count(k["orders"]), "customers": _count(k["customers"]),
                "revenue_eur": _euros(k["revenue_eur"])}
    if view == "demand":
        return {"accuracy": _accuracy(data["evaluation"]["accuracy"]),
                "tested_products": _count(data["evaluation"]["n"])}
    if view == "retention":
        return {"active_customers": _count(data["counts"]["active"]),
                "likely_to_leave": _count(data["counts"]["likely_to_leave"]),
                "listed_customers": _count(len(data["at_risk"])),
                "listed_spend_eur": _euros(data["decision"]["spend_12m_eur"])}
    if view == "supply":
        decision = data["overstock_decision"]
        return {"reorder_queue": _count(len(data["reorder_queue"])),
                "overstocked_skus": _count(decision["skus"]),
                "tied_capital_eur": _euros(decision["tied_capital_eur"])}
    if view == "model-checks":
        return {**{m["id"]: _accuracy(m["accuracy"]) for m in data["models"]},
                "churn": _accuracy(data["churn"]["accuracy"]), "demand": _accuracy(data["demand"]["accuracy"])}
    raise ValueError(f"no headline numbers for {view!r}")
