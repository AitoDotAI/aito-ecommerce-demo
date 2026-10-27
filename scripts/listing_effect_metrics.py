"""The metrics of data release 3a's effects (docs/verification/release3a-prereg.md): an offer and a list price
on the click and the purchase, pictures, description and advertising.

Each reads one generated data dir (`Fixtures`) and returns one ratio. Three rates describe a group of the shop's
list showings: click-through (clicks ÷ showings), purchases per click and purchases per showing.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Callable

from scripts.planted_effect_metrics import Fixtures

RATES = {"ctr": ("clicked", "showings"), "per click": ("purchased", "clicked"), "per showing": ("purchased", "showings")}


def _counts(fx: Fixtures, group: Callable[[dict], str | None], matched: bool) -> dict[str, dict[str, dict[str, int]]]:
    """group → product → {showings, clicked, purchased}, over customers' list showings."""
    state = fx.state()
    counts: dict[str, dict[str, dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for imp in fx.impressions():
        name = group(state[imp["product_state"]])
        if name is None:
            continue
        cell = counts[name][imp["product_sku"]]
        cell["showings"] += 1
        cell["clicked"] += imp["clicked"]
        cell["purchased"] += imp["purchased"]
    return counts


def rate_ratio(fx: Fixtures, group: Callable[[dict], str | None], high: str, low: str, rate: str,
               matched: bool = False) -> float:
    """`rate` of the `high` group ÷ the `low` group's. `matched`: only products shown in both, so the products
    are the same on both sides."""
    counts = _counts(fx, group, matched)
    skus = set(counts[high]) & set(counts[low]) if matched else None

    def pooled(name: str) -> float:
        top, bottom = RATES[rate]
        cells = [c for sku, c in counts[name].items() if skus is None or sku in skus]
        return sum(c[top] for c in cells) / sum(c[bottom] for c in cells)
    return pooled(high) / pooled(low)


def _band(state: dict) -> str | None:
    return state["discount_band"] if state["discount_band"] in ("none", "20+") else None


def _varying_list_price(fx: Fixtures) -> set[str]:
    """Products whose list price index takes 3 or more values: the dynamic ones, not a single rise."""
    seen = defaultdict(set)
    for st in fx.load("product_states"):
        seen[st["product_sku"]].add(st["list_price_index"])
    return {sku for sku, values in seen.items() if len(values) >= 3}


def offer_purchase_over_click(fx: Fixtures) -> float:
    """Q3: purchases per showing ÷ click-through, at a 20 %+ offer against none (same products)."""
    return rate_ratio(fx, _band, "20+", "none", "per showing", True) / rate_ratio(fx, _band, "20+", "none", "ctr", True)


def offer_click_through(fx: Fixtures) -> float:
    return rate_ratio(fx, _band, "20+", "none", "ctr", True)


def offer_units(fx: Fixtures) -> float:
    """Q3b: mean units of a month at a 20 %+ offer ÷ the same products' with none."""
    state = fx.state()
    units: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for ms in fx.load("monthly_sales"):
        band = _band(state[ms["product_state"]])
        if band:
            units[band][ms["product_sku"]].append(ms["units_sold"])
    shared = set(units["20+"]) & set(units["none"])
    mean = lambda band: (sum(sum(units[band][s]) for s in shared) / sum(len(units[band][s]) for s in shared))
    return mean("20+") / mean("none")


def _list_price_group(varying: set[str]) -> Callable[[dict], str | None]:
    def group(state: dict) -> str | None:
        if state["product_sku"] not in varying or state["discount_band"] != "none":
            return None
        index = state["list_price_index"]
        return "cut" if index <= 0.90 else "rise" if index >= 1.05 else None
    return group


def list_price_elasticity(fx: Fixtures) -> float:
    """Q2: the elasticity the units imply, ε in units ∝ list_price_index^ε, over the dynamic products' months
    without an offer. A Poisson regression with a free level per product (the conditional likelihood, solved by
    Newton's method): each product is compared with itself, every price point counts. ADR 0049's A1 asks Aito
    for the same number."""
    state = fx.state()
    varying = _varying_list_price(fx)
    series: dict[str, list[tuple[float, int]]] = defaultdict(list)
    for ms in fx.load("monthly_sales"):
        st = state[ms["product_state"]]
        if ms["product_sku"] in varying and st["discount_band"] == "none":
            series[ms["product_sku"]].append((math.log(st["list_price_index"]), ms["units_sold"]))
    eps = 0.0
    for _ in range(50):
        score = information = 0.0
        for rows in series.values():
            total = sum(y for _, y in rows)
            weights = [math.exp(eps * x) for x, _ in rows]
            norm = sum(weights)
            mean = sum(w * x for w, (x, _) in zip(weights, rows)) / norm
            var = sum(w * x * x for w, (x, _) in zip(weights, rows)) / norm - mean ** 2
            score += sum(y * x for x, y in rows) - total * mean
            information += total * var
        step = score / information
        eps += step
        if abs(step) < 1e-9:
            return eps
    raise RuntimeError(f"the list price elasticity did not converge: {eps}")


def list_price_purchases(fx: Fixtures) -> float:
    """Q2a: purchases per showing, a list price at or below 0.90 ÷ at or above 1.05."""
    return rate_ratio(fx, _list_price_group(_varying_list_price(fx)), "cut", "rise", "per showing")


def list_price_click_through(fx: Fixtures) -> float:
    """Q2a: the same, click-through."""
    return rate_ratio(fx, _list_price_group(_varying_list_price(fx)), "cut", "rise", "ctr")


def list_price_purchase_over_click(fx: Fixtures) -> float:
    """Q2a: the purchase response ÷ the click's: above 1, the list price weighs on the purchase more."""
    return list_price_purchases(fx) / list_price_click_through(fx)


def images(fx: Fixtures, rate: str) -> float:
    """Q4: 4+ pictures ÷ 0–1."""
    return rate_ratio(fx, lambda st: st["image_count"], "4+", "0-1", rate)


def description(fx: Fixtures, rate: str) -> float:
    """Q5: a rich description ÷ a thin one."""
    return rate_ratio(fx, lambda st: st["description_quality"], "rich", "thin", rate)


def ads(fx: Fixtures, rate: str) -> float:
    """Q6: a banner ÷ none."""
    return rate_ratio(fx, lambda st: st["ad_level"], "banner", "none", rate)


def banner_showings(fx: Fixtures) -> float:
    """Q6: mean recorded showings of a product-month with a banner ÷ with none."""
    state = fx.state()
    showings = defaultdict(list)
    for ms in fx.load("monthly_sales"):
        showings[state[ms["product_state"]]["ad_level"]].append(ms["showings"])
    return (sum(showings["banner"]) / len(showings["banner"])) / (sum(showings["none"]) / len(showings["none"]))
