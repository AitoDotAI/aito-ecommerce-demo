"""What each customer earned the shop (ADR 0053): profit, not revenue.

Per customer, from the release's fixtures:

  gross profit = for each line not returned: (price paid - unit cost) x quantity
  profit       = gross profit - what the shop spent on actions for them (`customer_actions.cost_eur`)

The price paid is the product state's price (offers included), the unit cost is the inventory's. A returned line earns
nothing: the refund is assumed to return the goods to stock. There is no delivery, payment or staff cost in the data, so
this is profit after products and the shop's own actions, not a full P&L. The shop's gross margin is profit over the
price paid for the lines kept; the response table uses it to turn the action table's 30-day spend into profit.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import median

from src.customer_traits import TOO_FEW


def profit_by_customer(order_lines: list[dict], orders: dict[str, dict], states: dict[str, dict],
                       unit_cost: dict[str, float], actions: list[dict], last_12_from: str) -> dict[str, dict]:
    out: dict[str, dict] = defaultdict(lambda: {"net_revenue_eur": 0.0, "gross_profit_eur": 0.0, "gross_profit_12m_eur": 0.0,
                                                "action_cost_eur": 0.0, "returned_lines": 0})
    for line in order_lines:
        order = orders[line["order_id"]]
        entry = out[order["customer_id"]]
        if line["returned"]:
            entry["returned_lines"] += 1
            continue
        paid = states[line["product_state"]]["price_eur"] * line["qty"]
        earned = paid - unit_cost[line["product_sku"]] * line["qty"]
        entry["net_revenue_eur"] += paid
        entry["gross_profit_eur"] += earned
        entry["gross_profit_12m_eur"] += earned if order["month"] >= last_12_from else 0.0
    for action in actions:
        out[action["customer_id"]]["action_cost_eur"] += action["cost_eur"]
    for entry in out.values():
        entry["profit_eur"] = entry["gross_profit_eur"] - entry["action_cost_eur"]
    return dict(out)


def gross_margin(by_customer: dict[str, dict]) -> float:
    revenue = sum(c["net_revenue_eur"] for c in by_customer.values())
    return sum(c["gross_profit_eur"] for c in by_customer.values()) / revenue


def distribution(by_customer: dict[str, dict], customer_ids: list[str]) -> dict:
    """How the profit of these customers is spread: the median, the share the top tenth earns, and how many lose money."""
    values = sorted(by_customer[cid]["profit_eur"] for cid in customer_ids if cid in by_customer)
    top = values[len(values) - max(1, len(values) // 10):]
    return {"customers": len(values), "median_eur": round(values[len(values) // 2], 2),
            "top_tenth_share": round(sum(top) / sum(values), 3), "losing_money": sum(v < 0 for v in values)}


def margin_bands(by_customer: dict[str, dict], customer_ids: list[str]) -> tuple[dict[str, str], float]:
    """Each customer's basket margin (gross profit over the price paid for the lines kept) as "high-margin" or "low-margin",
    cut at the median customer's. A customer with nothing kept has no margin: they are `TOO_FEW`, and do not move the median."""
    margin = {cid: by_customer[cid]["gross_profit_eur"] / by_customer[cid]["net_revenue_eur"]
              for cid in customer_ids if cid in by_customer and by_customer[cid]["net_revenue_eur"] > 0}
    cut = round(median(margin.values()), 3)
    return {cid: ("high-margin" if margin[cid] >= cut else "low-margin") if cid in margin else TOO_FEW for cid in customer_ids}, cut
