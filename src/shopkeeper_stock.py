"""The stock routine as a rule (ADR 0057): reorder and overstock steps over the Supply snapshot, judged by a gate of its own.

There is no lift here, so the evidence is what the shop observed: the units sold in the planning window. A reorder is acted on when
enough was sold, the order is within the store's limit and the stock is nearly out; a large order is always a person's. A markdown is
a price change, so it is only ever suggested, and only when Aito's discount sweep says it clears the excess. Nothing is ordered or
repriced: a run is simulated. `build_stock_run` is deterministic over the snapshot, so a test rebuilds it and compares it with the stored file.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from src.shopkeeper_gate import ACT, NEVER_AUTO, QUIET, SUGGEST

ROOT = Path(__file__).resolve().parent.parent
SUPPLY_SNAPSHOT = ROOT / "data" / "precomputed" / "v2-master" / "supply.json"
STOCK_RUN = ROOT / "data" / "agent_runs" / "stock.json"


@dataclass(frozen=True)
class StockSettings:
    min_recent_units: int = 5           # units sold in the planning window: fewer is too little to base an order on
    order_limit_eur: float = 500.0      # an order above this is always a person's
    urgent_share: float = 0.5           # the stock at or below this share of the reorder point is urgent

    def __post_init__(self):
        if not 0 <= self.urgent_share <= 1:
            raise ValueError(f"urgent_share must be between 0 and 1, got {self.urgent_share}")
        if self.order_limit_eur < 0:
            raise ValueError(f"order_limit must not be negative, got {self.order_limit_eur}")
        if self.min_recent_units < 0:
            raise ValueError(f"min_recent_units must not be negative, got {self.min_recent_units}")


def build_stock_run(snapshot: dict, release: str) -> dict:
    steps = [{"kind": "reorder", "sku": r["sku"], "name": r["name"], "category": r["category"], "supplier": r["supplier"],
              "lead_time_days": r["lead_time_days"], "current_stock": r["current_stock"], "reorder_point": r["reorder_point"],
              "recent_units": r["recent_units"], "order_qty": r["order_qty"], "order_cost_eur": r["order_cost_eur"],
              "revenue_at_risk_eur": r["revenue_at_risk_eur"]} for r in snapshot["reorder_queue"]]
    steps += [{"kind": "overstock", "sku": o["sku"], "name": o["name"], "category": o["category"], "current_stock": o["current_stock"],
               "excess_units": o["excess_units"], "tied_capital_eur": o["tied_capital_eur"], "markdown": o["markdown"]} for o in snapshot["overstock"]]
    return {"id": "stock", "routine": "stock", "title": "Stock-aware morning check", "release": release, "as_of_month": snapshot["planning_month"],
            "simulated": True, "source": "data/precomputed/v2-master/supply.json (the snapshot Supply serves)", "steps": steps}


def decide_stock_steps(run: dict, settings: StockSettings) -> list[dict]:
    return [{**step, **_decide(step, settings)} for step in run["steps"]]


def _decide(step: dict, s: StockSettings) -> dict:
    if step["kind"] == "overstock":
        return _decide_overstock(step)
    units, cost = step["recent_units"], step["order_cost_eur"]
    if units < s.min_recent_units:
        return {"outcome": QUIET, "reason": f"Only {units} units sold in the planning window; the rule asks for {s.min_recent_units} before it orders."}
    if cost > s.order_limit_eur:
        return {"outcome": NEVER_AUTO, "reason": f"An order of {cost:,.0f} € is above the {s.order_limit_eur:,.0f} € the rule may place; {units} units sold."}
    if step["current_stock"] <= s.urgent_share * step["reorder_point"]:
        return {"outcome": ACT, "reason": f"{units} units sold, stock {step['current_stock']} against a reorder point of {step['reorder_point']}, "
                                          f"order of {cost:,.0f} € within the {s.order_limit_eur:,.0f} € limit."}
    return {"outcome": SUGGEST, "reason": f"{units} units sold; stock {step['current_stock']} is above {s.urgent_share:.0%} of the reorder point {step['reorder_point']}: not urgent yet."}


def _decide_overstock(step: dict) -> dict:
    markdown = step["markdown"]
    if markdown["action"] == "markdown":
        return {"outcome": SUGGEST, "reason": f"A markdown of {markdown['discount_pct']} % clears {markdown['units_cleared']} of {step['excess_units']} excess units "
                                              f"in {markdown['weeks_to_clear']:.0f} weeks; a price change is always a person's."}
    if markdown["action"] == "hold":
        return {"outcome": QUIET, "reason": "Aito's sweep says to hold: waiting clears it as fast as a discount would."}
    return {"outcome": QUIET, "reason": f"A markdown of {markdown['discount_pct']} % would not clear the excess: {markdown['units_cleared']} of {step['excess_units']} units."}


def tally_stock(decided: list[dict]) -> dict:
    """Steps per outcome, and for the reorders in each what they would order and the revenue they protect."""
    summary = {o: {"steps": 0, "order_cost_eur": 0.0, "revenue_at_risk_eur": 0.0} for o in (ACT, SUGGEST, NEVER_AUTO, QUIET)}
    for step in decided:
        group = summary[step["outcome"]]
        group["steps"] += 1
        if step["kind"] == "reorder" and step["outcome"] != QUIET:
            group["order_cost_eur"] = round(group["order_cost_eur"] + step["order_cost_eur"], 2)
            group["revenue_at_risk_eur"] = round(group["revenue_at_risk_eur"] + step["revenue_at_risk_eur"], 2)
    return summary


def load_stock_run() -> dict:
    return json.loads(STOCK_RUN.read_text())
