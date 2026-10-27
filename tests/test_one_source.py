"""ADR 0045: one source for showings and sales.

Every sale is a purchase in a session, so the units a product sold and the
showings that sold them are one record. O1 of
docs/verification/actionable-states-prereg.md, and the partial pet profile.
O2–O3 are judged against nulls by `./do planted-effects`; O4 runs on the
loaded env.
"""

from collections import Counter, defaultdict

from tests.fixture_joins import load


def _lines_by_customer_month() -> dict[tuple[str, str], Counter]:
    customer_month = {o["order_id"]: (o["customer_id"], o["month"]) for o in load("orders.json")}
    lines: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for ln in load("order_lines.json"):
        lines[customer_month[ln["order_id"]]][ln["product_sku"]] += ln["qty"]
    return lines


def test_o1_units_sold_are_the_sum_of_that_months_purchased_order_lines():
    month_of = {o["order_id"]: o["month"] for o in load("orders.json")}
    units = Counter()
    for ln in load("order_lines.json"):
        units[(ln["product_sku"], month_of[ln["order_id"]])] += ln["qty"]
    wrong = [(r["product_sku"], r["month"], r["units_sold"], units[(r["product_sku"], r["month"])])
             for r in load("monthly_sales.json") if r["units_sold"] != units[(r["product_sku"], r["month"])]]
    assert not wrong, wrong[:5]
    covered = {(r["product_sku"], r["month"]) for r in load("monthly_sales.json")}
    assert set(units) <= covered


def test_o1_every_purchased_impression_has_its_order_line():
    lines = _lines_by_customer_month()
    contexts = {c["context_id"]: c for c in load("contexts.json")}
    missing = []
    for imp in load("impressions.json"):
        if not imp["purchased"]:
            continue
        ctx = contexts[imp["context"]]
        if imp["product_sku"] not in lines.get((ctx.get("customer"), ctx["month"]), {}):
            missing.append(imp["impression_id"])
    assert not missing, missing[:5]


def test_o1_a_consenting_customers_order_lines_were_each_a_purchased_showing():
    consent = {c["customer_id"]: c["consent_behavioural"] for c in load("customers.json")}
    contexts = {c["context_id"]: c for c in load("contexts.json")}
    shown_bought = defaultdict(set)
    for imp in load("impressions.json"):
        if imp["purchased"]:
            ctx = contexts[imp["context"]]
            shown_bought[(ctx["customer"], ctx["month"])].add(imp["product_sku"])
    unshown = [(key, sku) for key, skus in _lines_by_customer_month().items() if consent[key[0]]
               for sku in skus if sku not in shown_bought[key]]
    assert not unshown, unshown[:5]


def test_monthly_sales_carry_the_price_index_and_the_offer_band_of_their_state():
    states = {s["product_state_id"]: s for s in load("product_states.json")}
    for r in load("monthly_sales.json")[:3000]:
        st = states[r["product_state"]]
        assert r["discount_band"] == st["discount_band"]
        # ADR 0049: the effective price against the product's original list price, so the list price and the
        # offer both show in it.
        assert abs(r["price_index"] - st["list_price_index"] * st["price_eur"] / st["list_price_eur"]) < 0.002


def test_about_two_in_five_customers_declare_a_pet_profile():
    customers = load("customers.json")
    share = sum("pets" in c for c in customers) / len(customers)
    assert 0.35 <= share <= 0.45, f"{share:.1%}"
    assert all("pets" in c for c in customers if "dog_size" in c)


def test_pets_from_orders_are_the_pet_types_of_the_customers_earlier_orders():
    products = {p["sku"]: p["pet_type"] for p in load("products.json")}
    bought = defaultdict(list)    # customer → [(month, pet type)]
    for o in load("orders.json"):
        bought[o["customer_id"]] += [(o["month"], products[s]) for s in o["skus"].split()]
    for ctx in load("contexts.json")[:5000]:
        if "customer" not in ctx:
            continue
        expected = sorted({pet for month, pet in bought[ctx["customer"]] if month < ctx["month"]})
        assert ctx.get("pets_from_orders", "").split() == expected, ctx["context_id"]
