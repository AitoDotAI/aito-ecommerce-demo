"""The raw rows behind a Customers selection (ADR 0055): sales by product, orders, and individual feedback.

`build_rows` keeps, for each profiled customer, their orders and order lines (`data/customer_profiles/rows.json`, written by
`./do customer-profiles`); reviews and NPS answers are read from the shop's own tables. A row says what happened and never
who it happened to: no name, no customer id, no contact detail. A selection under the minimum size is not shown row by row
(the route refuses it before it gets here).
"""

from __future__ import annotations

from collections import defaultdict

TABS = ("sales", "orders", "reviews", "nps")
PAGE_MAX = 100


def build_rows(customer_ids: set[str], orders: list[dict], order_lines: list[dict], states: dict[str, dict], products: dict[str, dict]) -> dict:
    """{"customers": id -> {"orders": [[order, month, total, lines, returned lines]], "lines": [[sku, month, qty, returned, paid]]}, "products": ...}."""
    owner = {o["order_id"]: (o["customer_id"], o["month"]) for o in orders if o["customer_id"] in customer_ids}
    out: dict[str, dict] = {cid: {"orders": [], "lines": []} for cid in sorted(customer_ids)}
    lines_of: dict[str, list[dict]] = defaultdict(list)
    for line in order_lines:
        if line["order_id"] in owner:
            lines_of[line["order_id"]].append(line)
    for o in orders:
        if o["order_id"] in owner:
            mine = lines_of[o["order_id"]]
            out[o["customer_id"]]["orders"].append([o["order_id"], o["month"], o["total_eur"], len(mine), sum(1 for ln in mine if ln["returned"])])
            for ln in mine:
                paid = 0.0 if ln["returned"] else round(states[ln["product_state"]]["price_eur"] * ln["qty"], 2)
                out[o["customer_id"]]["lines"].append([ln["product_sku"], o["month"], ln["qty"], int(ln["returned"]), paid])
    used = {sku for c in out.values() for sku, *_ in c["lines"]}
    return {"customers": out, "products": {sku: {k: products[sku][k] for k in ("name", "brand", "category", "pet_type")} for sku in sorted(used)}}


def page_of(rows: dict, reviews: list[dict], answers: list[dict], customer_ids: list[str], tab: str, months: set[str] | None,
            offset: int, limit: int) -> dict:
    """One page of a tab for the customers `customer_ids`, in `months` only when given."""
    if tab not in TABS:
        raise ValueError(f"No tab {tab!r}; the tabs are {', '.join(TABS)}")
    if not 1 <= limit <= PAGE_MAX or offset < 0:
        raise ValueError(f"A page is 1 to {PAGE_MAX} rows (limit) from a row that is not negative (offset); got limit {limit}, offset {offset}")
    selected = set(customer_ids)
    keep = (lambda month: True) if months is None else (lambda month: month in months)
    listed = {"sales": _sales, "orders": _orders, "reviews": _reviews, "nps": _nps}[tab](rows, reviews, answers, selected, keep)
    return {"tab": tab, "total": len(listed), "offset": offset, "rows": listed[offset:offset + limit]}


def _sales(rows: dict, reviews, answers, selected: set[str], keep) -> list[dict]:
    units: dict[str, list] = defaultdict(lambda: [0, 0, 0.0, set()])
    for cid in selected:
        for sku, month, qty, returned, paid in rows["customers"].get(cid, {"lines": []})["lines"]:
            if keep(month):
                entry = units[sku]
                entry[0] += 0 if returned else qty
                entry[1] += qty if returned else 0
                entry[2] += paid
                entry[3].add(cid)
    listed = [{"product": rows["products"][sku]["name"], "brand": rows["products"][sku]["brand"], "category": rows["products"][sku]["category"],
               "units": u, "returned_units": r, "revenue_eur": round(rev, 2), "customers": len(who)} for sku, (u, r, rev, who) in units.items()]
    return sorted(listed, key=lambda r: (-r["revenue_eur"], r["product"]))


def _orders(rows: dict, reviews, answers, selected: set[str], keep) -> list[dict]:
    listed = [{"order": o, "month": month, "total_eur": total, "lines": lines, "returned_lines": returned}
              for cid in selected for o, month, total, lines, returned in rows["customers"].get(cid, {"orders": []})["orders"] if keep(month)]
    return sorted(listed, key=lambda r: (r["month"], r["order"]), reverse=True)


def _reviews(rows: dict, reviews: list[dict], answers, selected: set[str], keep) -> list[dict]:
    names = {sku: p["name"] for sku, p in rows["products"].items()}
    listed = [{"month": r["created_at"], "product": names.get(r["product_sku"], r["product_sku"]), "stars": r["rating"], "topic": r["category"],
               "replied": r["replied"], "text": r["text"]} for r in reviews if r["customer_id"] in selected and keep(r["created_at"])]
    return sorted(listed, key=lambda r: (r["month"], r["product"]), reverse=True)


def _nps(rows: dict, reviews, answers: list[dict], selected: set[str], keep) -> list[dict]:
    listed = [{"month": a["month"], "score": a["score"], "group": a["nps_group"], "also_wrote_a_negative_review": a["wrote_negative_review"], "comment": a.get("comment")}
              for a in answers if a["customer"] in selected and keep(a["month"])]
    return sorted(listed, key=lambda r: (r["month"], r["score"]), reverse=True)
