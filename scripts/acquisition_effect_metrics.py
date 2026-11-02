"""The metrics of ADR 0040's planted effects: sources, landings, conversion, who stays.

Read from one generated data dir; `scripts/planted_effects.py` compares them
between a planted generation and its null
(docs/verification/actionable-states-prereg.md).
"""
from __future__ import annotations

from types import SimpleNamespace

from data.acquisition import is_staple_line
from scripts.planted_effect_metrics import Fixtures


def _share(rows, condition) -> float:
    rows = list(rows)
    assert rows, "no rows to take a share of"
    return sum(1 for r in rows if condition(r)) / len(rows)


def landing_share(fx: Fixtures, sources: tuple[str, ...], landing: str) -> float:
    """F1a, F1c: P(the visit lands on `landing` | it came from one of `sources`)."""
    return _share((c for c in fx.load("contexts") if c["source"] in sources), lambda c: c["landing"] == landing)


def social_toys_and_treats(fx: Fixtures) -> float:
    """F1b: P(landing category is toys or treats | social, a landing with a category)."""
    return _share((c for c in fx.load("contexts") if c["source"] == "social" and "landing_category" in c),
                  lambda c: c["landing_category"] in ("toys", "treats"))


def conversion(fx: Fixtures, source: str) -> float:
    """F2: first-order visits ÷ every new visitor's visit, from `source`."""
    new_visits = [c for c in fx.load("contexts") if c["source"] == source
                  and ("customer" not in c or c["first_order"])]
    return _share(new_visits, lambda c: c["first_order"])


def _customers(fx: Fixtures) -> list[dict]:
    traits = fx.traits()
    return [{**c, **traits[c["customer_id"]]} for c in fx.load("customers")]


def sensitivity_by_source(fx: Fixtures, sensitivity: str, source: str) -> float:
    """F3: P(`sensitivity` high | first source) ÷ P(… | any other first source)."""
    rows = _customers(fx)
    high = lambda c: c[f"{sensitivity}_sensitivity"] == "high"
    return (_share((c for c in rows if c["first_source"] == source), high)
            / _share((c for c in rows if c["first_source"] != source), high))


def offer_share_of_purchases(fx: Fixtures, source: str) -> float:
    """F3c: on-offer share of purchased impressions, customers from `source` ÷ the others."""
    state = fx.state()
    first = {c["customer_id"]: c["first_source"] for c in fx.load("customers")}
    bought = [r for r in fx.impressions() if r["purchased"]]
    on_offer = lambda r: state[r["product_state"]]["on_offer"]
    return (_share((r for r in bought if first[r["customer_id"]] == source), on_offer)
            / _share((r for r in bought if first[r["customer_id"]] != source), on_offer))


def _staple_first(fx: Fixtures) -> dict[str, bool]:
    """customer → whether their first order held a staple (F5)."""
    products = {p["sku"]: SimpleNamespace(**p) for p in fx.load("products")}
    first: dict[str, dict] = {}
    for o in fx.load("orders"):
        if o["customer_id"] not in first or o["month"] < first[o["customer_id"]]["month"]:
            first[o["customer_id"]] = o
    return {cid: any(is_staple_line(products[s]) for s in o["skus"].split()) for cid, o in first.items()}


def regular_rate(fx: Fixtures, source: str | None = None, staple_first: bool | None = None) -> float:
    """F4, F5: the share who became regular, among customers it is known for."""
    staple = _staple_first(fx)
    rows = [c for c in fx.load("customers") if "became_regular" in c
            and (source is None or c["first_source"] == source)
            and (staple_first is None or staple[c["customer_id"]] == staple_first)]
    return _share(rows, lambda c: c["became_regular"])
