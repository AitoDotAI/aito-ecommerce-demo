"""How much clustering by customer widens a lift's interval.

A `_relate` hit counts rows: impressions, order lines, orders. Rows of
one customer are not independent. One search shows 6–14 products under
the same query, and a customer who buys often buys from many sessions,
so an interval that treats 53 purchases as 53 independent draws is too
narrow.

The standard correction is a design effect: the variance under cluster
sampling over the variance if the rows were independent. Kish's
approximation for a comparison between groups is

    deff ≈ 1 + (m − 1) · ρ_condition · ρ_value

where m is the size-weighted mean rows per customer and ρ the intra-
customer correlation of the condition (e.g. "purchased") and of the
related value (e.g. "rating 1–2"). We estimate ρ_condition from the data
and bound ρ_value by 1, so the result is an upper bound: intervals come
out wider than they need to be, never narrower.

ρ_condition needs, for every customer, their rows and the rows meeting
the condition. Two field-form `_relate`s on the customer column give
both: `fOnCondition` per customer under the population's `where` (their
rows), and under the condition's `where` (their rows meeting it).
"""

from __future__ import annotations

from dataclasses import dataclass

from src.aito_client import AitoClient, AitoError
from src.aito_compat import related_value


# Above the number of customers (3,000), so a full page raises.
CUSTOMER_LIMIT = 10_000


@dataclass(frozen=True)
class DesignEffect:
    customers: int
    rows_per_customer: float    # size-weighted mean, Σ n_i² / Σ n_i
    intra_customer_correlation: float
    design_effect: float        # 1 + (m − 1) · ρ


def customer_bodies(table: str, customer_field: str, population: dict, condition: dict) -> tuple[dict, dict]:
    def body(where: dict) -> dict:
        return {"from": table, "where": where, "relate": customer_field, "limit": CUSTOMER_LIMIT}

    return body(population), body(condition)


def rows_per_customer(hits: list[dict], field: str) -> dict[str, int]:
    """{customer: rows meeting the query's `where`} from a `_relate` on the
    customer column. Customers without such rows have no hit."""
    if len(hits) >= CUSTOMER_LIMIT:
        raise AitoError(f"_relate on {field} returned a full page of {CUSTOMER_LIMIT}; customers may be cut off")
    return {related_value(h, field): int(h["fs"]["fOnCondition"]) for h in hits}


def design_effect(population: dict[str, int], condition: dict[str, int]) -> DesignEffect:
    """ρ by the one-way ANOVA estimator for a binary outcome with unequal
    cluster sizes, clipped to [0, 1]."""
    stray = set(condition) - set(population)
    if stray:
        raise AitoError(f"{len(stray)} customers meet the condition but are not in the population, e.g. {sorted(stray)[:3]}")
    sizes = [n for n in population.values() if n > 0]
    hits = [condition.get(c, 0) for c, n in population.items() if n > 0]
    total, clusters = sum(sizes), len(sizes)
    if clusters < 2 or total <= clusters:
        raise AitoError(f"cannot estimate a design effect from {clusters} customers and {total} rows")

    rate = sum(hits) / total
    between = sum(n * (y / n - rate) ** 2 for n, y in zip(sizes, hits)) / (clusters - 1)
    within = sum(y - y * y / n for n, y in zip(sizes, hits)) / (total - clusters)
    n0 = (total - sum(n * n for n in sizes) / total) / (clusters - 1)
    denominator = between + (n0 - 1) * within
    rho = 0.0 if denominator == 0 else min(1.0, max(0.0, (between - within) / denominator))
    weighted_size = sum(n * n for n in sizes) / total
    return DesignEffect(
        customers=clusters,
        rows_per_customer=round(weighted_size, 1),
        intra_customer_correlation=round(rho, 4),
        design_effect=round(1 + (weighted_size - 1) * rho, 2),
    )
