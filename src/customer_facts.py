"""What the Customers view needs to know about each profiled customer, in one small file (ADR 0053).

A selection of conditions ("premium-leaning and dog owners") is any intersection of segments, far too many to store a
profile for each. So the app does not store profiles: it stores the facts per customer (traits, what they earned,
where they came from, their showing funnel, what they bought, their months) and counts a selection from them when it
is asked for. `data/customer_profiles/facts.json` is written by `./do customer-profiles` and holds profiled customers only.
"""

from __future__ import annotations

from collections import defaultdict

PET_KINDS = ("categories", "brands", "products")


def monthly_orders(orders: list[dict], order_lines: list[dict], states: dict[str, dict],
                   unit_cost: dict[str, float]) -> dict[str, dict[str, list]]:
    """customer -> month -> [orders placed, price paid on the lines kept, gross profit on them]; the same basis as profit and margin."""
    month_of = {o["order_id"]: (o["customer_id"], o["month"]) for o in orders}
    out: dict[str, dict[str, list]] = defaultdict(dict)
    for o in orders:
        out[o["customer_id"]].setdefault(o["month"], [0, 0.0, 0.0])[0] += 1
    for line in order_lines:
        if not line["returned"]:
            customer, month = month_of[line["order_id"]]
            paid = states[line["product_state"]]["price_eur"] * line["qty"]
            out[customer][month][1] += paid
            out[customer][month][2] += paid - unit_cost[line["product_sku"]] * line["qty"]
    return out


def build_facts(traits: list[dict], customers: dict[str, dict], funnel: dict[str, dict], first: dict[str, dict[str, str]],
                bought: dict[str, dict[str, dict[str, set[str]]]], shares: dict[str, dict[str, float]],
                months: dict[str, dict[str, list]], answers: list[dict], product_names: dict[str, str]) -> dict:
    """Facts for the profiled customers; a customer without consent is not here at all."""
    nps: dict[str, list] = defaultdict(list)
    for a in answers:
        nps[a["customer"]].append([a["month"], a["nps_group"]])
    out = {}
    for t in traits:
        if not t["profiled"]:
            continue
        cid, c = t["customer_id"], customers[t["customer_id"]]
        out[cid] = {
            "offer": t["offer"], "price": t["price"], "rating": t["rating"], "margin": t["margin"], "status": t["status"], "pets": t["pets"], "diets": t["diets"],
            "churned": bool(c["churned"]), "total_spent_eur": round(c["total_spent_eur"], 2),
            "net_revenue_eur": round(c["net_revenue_eur"], 2), "gross_profit_eur": round(c["gross_profit_eur"], 2),
            "gross_profit_12m_eur": round(c["gross_profit_12m_eur"], 2), "profit_eur": round(c["profit_eur"], 2),
            "funnel": [funnel.get(cid, {}).get(stage, 0) for stage in ("impressions", "clicks", "carts", "purchases")],
            "first": first.get(cid),
            "months": {m: [n, round(eur, 2), round(gross, 2)] for m, (n, eur, gross) in sorted(months.get(cid, {}).items())},
            "nps": sorted(nps.get(cid, [])),
            "bought": {pet: {kind: sorted(items[kind]) for kind in PET_KINDS} for pet, items in bought[cid].items()},
        }
    named = {sku for c in out.values() for items in c["bought"].values() for sku in items["products"]}
    return {"customers": out, "product_names": {sku: product_names[sku] for sku in sorted(named)},
            "shares": {var: {cid: round(s, 4) for cid, s in by_customer.items() if cid in out} for var, by_customer in sorted(shares.items())}}
