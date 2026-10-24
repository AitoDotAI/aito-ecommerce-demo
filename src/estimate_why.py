"""Explain a k-NN `_estimate` in the units it estimates: the `?` popover
on Inventory and Demand.

Aito's default `_estimate` model averages the k nearest past rows
("neighbours"). Its `why` is a `weightedAverage` of `neighborContext`
nodes, and each neighbour's value is the same regression the price
what-if uses (ADR 0029), plus that neighbour's own residual:

    neighbour_i = mean + Σ field terms + residual_i            form "add"
    neighbour_i = exp(mean + Σ field terms + residual_i)       form "multiply"

The field terms are the query's own (`units_last_month: 30`,
`season: spring`, ...) and identical in every neighbour; only the residual
differs. So the average splits exactly into a base, one contribution per
field, and one "similar past months" contribution: the neighbours' average
residual. On data with zero-sale months (the shape seen on env
`observable`, 2026-10-24) the form is "add" and every term is in units.

The estimate Aito returns can differ from the average its `why` describes
(27.53 against 27.47 for SKU-PT-0206; 8.08 against 10.36 for SKU-PT-0155).
That gap is shown as its own row, not spread over the others.

When the neighbours don't share their field terms, the split above is not
true, and the popover shows the top neighbour's terms as Aito returned
them, labelled as unconverted (form "raw").
"""

from __future__ import annotations

import math
from typing import Any

from src.aito_client import AitoError

# A gap smaller than this (in units, or as a multiplier minus one) is
# rounding, not a difference worth a row.
GAP_TOLERANCE = 1e-6


def explain_estimate(why: Any, estimate: float, *, field_label: str) -> dict | None:
    """The popover payload for a k-NN `_estimate` `why`, or None without one.

    Returns `{kind, form, estimate, field_label, base, neighbours, components}`
    where each component is `{type, label, effect}`: units added (form
    "add"), a multiplier (form "multiply"), or Aito's raw value (form "raw").
    Base and components chain to `estimate` in the first two forms.
    """
    if why is None:
        return None
    if not (isinstance(why, dict) and why.get("type") == "weightedAverage" and why.get("components")):
        raise AitoError(f"unexpected _estimate why, expected a weightedAverage: {str(why)[:300]}")
    neighbours = [_neighbour(c) for c in why["components"]]
    payload = {"kind": "estimate", "estimate": estimate, "field_label": field_label,
               "neighbours": len(neighbours)}
    first = neighbours[0]
    if not all(_same_regression(first, n) for n in neighbours):
        return {**payload, **_raw(why)}

    multiply = first["form"] == "multiply"
    weights = [n["weight"] for n in neighbours]
    if multiply:
        base = math.exp(first["mean"])
        fields = [_field(f, math.exp(v)) for f, v in first["fields"]]
        similar = _weighted_mean([math.exp(n["residual"]) for n in neighbours], weights)
        average = base * math.prod(c["effect"] for c in fields) * similar
        gap = estimate / average
        has_gap = abs(gap - 1) > GAP_TOLERANCE
    else:
        base = first["mean"]
        fields = [_field(f, v) for f, v in first["fields"]]
        similar = _weighted_mean([n["residual"] for n in neighbours], weights)
        average = base + sum(c["effect"] for c in fields) + similar
        gap = estimate - average
        has_gap = abs(gap) > GAP_TOLERANCE

    stated = why.get("value")
    if isinstance(stated, (int, float)) and not math.isclose(stated, average, rel_tol=1e-6, abs_tol=1e-6):
        raise AitoError(f"_estimate why: the neighbours average {average}, but the why says {stated}")

    size = (lambda c: abs(math.log(c["effect"]))) if multiply else (lambda c: abs(c["effect"]))
    components = sorted(fields, key=size, reverse=True)
    components.append({"type": "neighbours", "effect": similar,
                       "label": f"Similar past months ({len(neighbours)} neighbours)"})
    if has_gap:
        components.append({"type": "unexplained", "effect": gap,
                           "label": "Not in the why: the estimate vs. the neighbours' average"})
    return {**payload, "form": "multiply" if multiply else "add", "base": base, "components": components}


def regression_terms(why: Any) -> tuple[str, list[dict]]:
    """`exp(sum(terms))` or `sum(terms)`: the two shapes Aito's regression takes."""
    if isinstance(why, dict) and why.get("type") == "sum" and isinstance(why.get("terms"), list):
        return "add", why["terms"]
    if (isinstance(why, dict) and why.get("type") == "exponent"
            and isinstance(why.get("power"), dict) and why["power"].get("type") == "sum"):
        return "multiply", why["power"]["terms"]
    raise AitoError(f"unexpected _estimate why, expected exp(sum(…)) or sum(…): {str(why)[:300]}")


def term_label(field: str, value: object) -> str:
    """How a regression term's field and value read in a row."""
    match field:
        case "price_eur":
            return f"Price €{float(value):.2f}"
        case "units_last_month":
            return f"Sold {value} last month"
        case "product_sku":
            return "This product"
        case _:
            return f"{field.replace('_', ' ').capitalize()}: {str(value).replace('-', ' ')}"


def _neighbour(component: Any) -> dict:
    node = component.get("value") if isinstance(component, dict) else None
    if not (isinstance(node, dict) and node.get("type") == "neighborContext"):
        raise AitoError(f"unexpected _estimate neighbour: {str(component)[:300]}")
    form, terms = regression_terms(node.get("adjustments"))
    mean, residual, fields = None, 0.0, []
    for term in terms:
        if term["type"] == "mean centering":
            mean = term["value"]
        elif term["type"] == "input" and term.get("name") == "residual":
            residual = term["value"]
        elif term["type"] == "regression" and len(term.get("proposition") or {}) == 1:
            [(field, value)] = term["proposition"].items()
            fields.append(((field, value), term["value"]))
        else:
            raise AitoError(f"unexpected term in an _estimate neighbour: {term}")
    if mean is None:
        raise AitoError(f"_estimate neighbour has no mean term: {str(node)[:300]}")
    total = mean + residual + sum(v for _, v in fields)
    chained = math.exp(total) if form == "multiply" else total
    if not math.isclose(chained, node["value"], rel_tol=1e-6, abs_tol=1e-6):
        raise AitoError(f"_estimate neighbour's terms give {chained}, its value is {node['value']}")
    return {"form": form, "mean": mean, "residual": residual, "fields": sorted(fields, key=lambda f: str(f[0])),
            "weight": float(component.get("weight", 1.0))}


def _same_regression(a: dict, b: dict) -> bool:
    """Whether two neighbours carry the same mean and field terms."""
    return (a["form"] == b["form"] and math.isclose(a["mean"], b["mean"], rel_tol=1e-9)
            and [f for f, _ in a["fields"]] == [f for f, _ in b["fields"]]
            and all(math.isclose(x, y, rel_tol=1e-9, abs_tol=1e-12)
                    for (_, x), (_, y) in zip(a["fields"], b["fields"])))


def _field(field_value: tuple[str, object], effect: float) -> dict:
    field, value = field_value
    return {"type": "field", "label": term_label(field, value), "effect": effect}


def _weighted_mean(values: list[float], weights: list[float]) -> float:
    return sum(v * w for v, w in zip(values, weights)) / sum(weights)


def _raw(why: dict) -> dict:
    top = max(why["components"], key=lambda c: float(c.get("weight", 0)))
    _, terms = regression_terms(top["value"]["adjustments"])
    components = [{"type": "raw", "effect": t["value"],
                   "label": term_label(*next(iter(t["proposition"].items()))) if t.get("proposition")
                   else t.get("name", t["type"])} for t in terms]
    return {"form": "raw", "base": None, "components": components}
