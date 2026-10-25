"""The metrics of ADR 0044's checks: declared interests, consent and sex.

Read from one generated data dir; `scripts/planted_effects.py` judges them
(docs/verification/actionable-states-prereg.md, ADR 0044 addendum).
"""
from __future__ import annotations

import math
from collections import defaultdict

from scripts.planted_effect_metrics import Fixtures

FOOD_AND_TREATS = ("dry-food", "wet-food", "treats")
TRAITS = ("segment", "lifestyle", "health_focus", "treat_affinity", "brand_loyalty",
          "discount_sensitivity", "stars_sensitivity", "newness_sensitivity", "labels_sensitivity")
MIN_GROUP = 100
MIN_CATEGORY_LINES = 1000


def _lines_with_buyer(fx: Fixtures):
    products = {p["sku"]: p for p in fx.load("products")}
    buyer = {o["order_id"]: o["customer_id"] for o in fx.load("orders")}
    for ln in fx.load("order_lines"):
        yield buyer[ln["order_id"]], products[ln["product_sku"]]


def natural_food_grain_free(fx: Fixtures) -> float:
    """C1: grain-free share of food and treat lines, `natural_food` declarers ÷ everyone else."""
    declares = {c["customer_id"]: "natural_food" in c.get("interests", "").split() for c in fx.load("customers")}
    counts = {True: [0, 0], False: [0, 0]}
    for customer, product in _lines_with_buyer(fx):
        if product["category"] in FOOD_AND_TREATS:
            cell = counts[declares[customer]]
            cell[0] += product.get("dietary") == "grain-free"
            cell[1] += 1
    (a, n_a), (b, n_b) = counts[True], counts[False]
    return (a / n_a) / (b / n_b)


def consent_rate_off(fx: Fixtures) -> float:
    """C2: how far the overall consent rate sits from 0.6."""
    customers = fx.load("customers")
    return abs(sum(c["consent_behavioural"] for c in customers) / len(customers) - 0.6)


def consent_largest_gap(fx: Fixtures) -> float:
    """C2: the largest |consent rate of a trait level − the overall rate|, levels of ≥ 100 customers."""
    traits = fx.traits()
    customers = fx.load("customers")
    overall = sum(c["consent_behavioural"] for c in customers) / len(customers)
    gaps = []
    for trait in TRAITS:
        by_level: dict[str, list[bool]] = defaultdict(list)
        for c in customers:
            by_level[traits[c["customer_id"]][trait]].append(c["consent_behavioural"])
        gaps += [abs(sum(v) / len(v) - overall) for v in by_level.values() if len(v) >= MIN_GROUP]
    return max(gaps)


def sex_largest_log_ratio(fx: Fixtures) -> float:
    """C3: the largest |log(category share of female buyers' lines ÷ of male buyers')|."""
    sex = {c["customer_id"]: c.get("sex") for c in fx.load("customers")}
    lines: dict[str, dict[str, int]] = {"female": defaultdict(int), "male": defaultdict(int)}
    for customer, product in _lines_with_buyer(fx):
        if sex[customer] in lines:
            lines[sex[customer]][product["category"]] += 1
    totals = {s: sum(by.values()) for s, by in lines.items()}
    ratios = [(lines["female"][cat] / totals["female"]) / (lines["male"][cat] / totals["male"])
              for cat in set(lines["female"]) | set(lines["male"])
              if lines["female"][cat] + lines["male"][cat] >= MIN_CATEGORY_LINES]
    return max(abs(math.log(r)) for r in ratios)
