"""Build the stored customer profiles from the release's fixtures (ADR 0053): traits per customer, segments, responses."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from src.customer_profit import distribution, gross_margin, profit_by_customer
from src.customer_relations import PET_GROUPS, preferences, relations
from src.customer_segments import response, segment_keys, segments
from src.customer_traits import reference_for, traits_for

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def _load(name: str) -> list[dict]:
    return json.loads((DATA / f"{name}.json").read_text())


LAST_12_MONTHS_FROM = "2025-05"       # the window Retention calls the last 12 months (ending 2026-04)


def build() -> tuple[dict, list[dict]]:
    """(summary, per-customer traits), a pure function of the fixtures and the release file."""
    customers = {c["customer_id"]: {**c, "revenue_eur": 0.0, "revenue_12m_eur": 0.0} for c in _load("customers")}
    orders = {}
    for o in _load("orders"):
        orders[o["order_id"]] = o["customer_id"]
        customers[o["customer_id"]]["revenue_eur"] += o["total_eur"]
        customers[o["customer_id"]]["revenue_12m_eur"] += o["total_eur"] if o["month"] >= LAST_12_MONTHS_FROM else 0.0
    products = {p["sku"]: p for p in _load("products")}
    states = {s["product_state_id"]: s for s in _load("product_states")}
    lines_of = defaultdict(list)
    for line in _load("order_lines"):
        lines_of[orders[line["order_id"]]].append(line)
    profits = profit_by_customer(_load("order_lines"), {o["order_id"]: o for o in _load("orders")}, states,
                                 {i["sku"]: i["unit_cost_eur"] for i in _load("inventory")}, _load("customer_actions"),
                                 LAST_12_MONTHS_FROM)
    margin = gross_margin(profits)
    zero = {"net_revenue_eur": 0.0, "gross_profit_eur": 0.0, "gross_profit_12m_eur": 0.0, "action_cost_eur": 0.0, "profit_eur": 0.0}
    for cid, customer in customers.items():
        customer.update(profits.get(cid, zero))
    ref = reference_for(list(products.values()), list(states.values()))
    traits = [traits_for(c, lines_of[cid], products, states, ref) for cid, c in customers.items()]
    bought = {cid: {pet: {"categories": set(), "brands": set(), "products": set()} for pet in PET_GROUPS} for cid in customers}
    for cid, lines in lines_of.items():
        for ln in lines:
            product = products[ln["product_sku"]]
            if product["pet_type"] in PET_GROUPS:
                mine = bought[cid][product["pet_type"]]
                mine["categories"].add(product["category"])
                mine["brands"].add(product["brand"])
                mine["products"].add(ln["product_sku"])
    release = json.loads((DATA / "release-env.json").read_text())["env"]
    for t in traits:
        if t["profiled"]:
            t["profit_eur"] = round(customers[t["customer_id"]]["profit_eur"], 2)
    keys_of = {t["customer_id"]: segment_keys(t) for t in traits}
    summary = {"release": release, "simulated": True, **segments(traits, customers), "gross_margin": round(margin, 3),
               "profit_distribution": distribution(profits, [t["customer_id"] for t in traits if t["profiled"]]),
               "response": response(_load("customer_actions"), margin, lambda row: keys_of.get(row["customer_id"], ())),
               "relations": relations(traits), "preferences": _named(preferences(traits, bought), products)}
    return summary, traits


def _named(prefs: dict, products: dict[str, dict]) -> dict:
    """Products are listed by sku; give each its name."""
    for entry in prefs.values():
        for row in entry["products"]:
            row["name"] = products[row["item"]]["name"]
    return prefs
