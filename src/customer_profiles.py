"""Build the stored customer profiles from the release's fixtures (ADR 0053): traits per customer, segments, responses."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from src.customer_profit import distribution, gross_margin, margin_bands, profit_by_customer
from src.customer_acquisition import first_sessions
from src.customer_facts import build_facts, monthly_orders
from src.customer_funnel import funnel_by_segment
from src.customer_preference_ranking import line_features, scores
from src.customer_relations import PET_GROUPS
from src.data_loader import split_showings
from src.customer_segments import definitions, segments
from src.customer_traits import NOT_PROFILED, reference_for, traits_for

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def _load(name: str) -> list[dict]:
    return json.loads((DATA / f"{name}.json").read_text())


LAST_12_MONTHS_FROM = "2025-05"       # the window Retention calls the last 12 months (ending 2026-04)


def build() -> tuple[dict, list[dict], dict]:
    """(summary, per-customer traits, per-customer facts), a pure function of the fixtures and the release file."""
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
    bands, margin_cut = margin_bands(customers, [t["customer_id"] for t in traits if t["profiled"]])
    for t in traits:
        t["margin"] = bands.get(t["customer_id"], NOT_PROFILED)
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
    ranked_lines = defaultdict(list)
    for cid, lines in lines_of.items():
        for ln in lines:
            product, state = products[ln["product_sku"]], states[ln["product_state"]]
            key = (product["category"], product["pet_type"])
            ranked_lines[cid].append({"pet": product["pet_type"],
                                      "features": line_features(product, state, ref.median_price[key], ref.mean_rating.get(key))})
    profiled_ids = {t["customer_id"] for t in traits if t["profiled"]}
    showings, _unranked = split_showings(_load("impressions"), _load("contexts"))
    context_customer = {c["context_id"]: c.get("customer") for c in _load("contexts")}
    funnel = funnel_by_segment(showings, context_customer, {cid: [cid] for cid in profiled_ids})   # one "segment" per customer
    facts = build_facts(traits, customers, funnel, first_sessions(list(customers.values()), _load("contexts")), bought,
                        scores(ranked_lines, profiled_ids), monthly_orders(_load("orders"), _load("order_lines"), states),
                        {sku: p["name"] for sku, p in products.items()})
    summary = {"release": release, "simulated": True, **segments(traits, customers), "gross_margin": round(margin, 3), "margin_cut": margin_cut,
               "profit_distribution": distribution(profits, sorted(profiled_ids)), "definitions": definitions()}
    return summary, traits, facts
