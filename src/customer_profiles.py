"""Build the stored customer profiles from the release's fixtures (ADR 0053): traits per customer, segments, responses."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from src.customer_segments import response, segments
from src.customer_traits import reference_for, traits_for

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def _load(name: str) -> list[dict]:
    return json.loads((DATA / f"{name}.json").read_text())


def build() -> tuple[dict, list[dict]]:
    """(summary, per-customer traits), a pure function of the fixtures and the release file."""
    customers = {c["customer_id"]: c for c in _load("customers")}
    orders = {o["order_id"]: o["customer_id"] for o in _load("orders")}
    products = {p["sku"]: p for p in _load("products")}
    states = {s["product_state_id"]: s for s in _load("product_states")}
    lines_of = defaultdict(list)
    for line in _load("order_lines"):
        lines_of[orders[line["order_id"]]].append(line)
    ref = reference_for(list(products.values()))
    traits = [traits_for(c, lines_of[cid], products, states, ref) for cid, c in customers.items()]
    release = json.loads((DATA / "release-env.json").read_text())["env"]
    summary = {"release": release, "simulated": True, **segments(traits, customers), "response": response(_load("customer_actions"))}
    return summary, traits
