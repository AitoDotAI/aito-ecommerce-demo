"""`customer_actions`: what the shop did for a customer in a month, and what followed (ADR 0051).

One row per action taken, "none" included, with the customer's context as the
shop could read it that month, the action and its parameters, and the
outcomes over the next 30 days. Which action works depends on the context;
the situations below are planted, and the tests judge each one.

  A1  An email works on customers who answered one before, and not on those
      who ignored the last ones.
  A2  A discount works on customers who mostly buy on offer, and gives margin
      away to the rest.
  A3  A voucher brings back lapsed customers (180 days and more).
  A4  An ad reaches customers who consented to tracking; to the others it does nothing.
  A5  An apology works on a customer with an open issue, and is wasted on the rest.
      An email to such a customer lands worse than usual.

The cost of an action is what it cost in that row: a sent email or an ad
costs when sent, a discount or a voucher only when the customer orders.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from data.planted_switches import ON, stream

ACTIONS = ("none", "email", "discount", "voucher", "ad", "apology")
EMAIL_COST_EUR = 0.50
AD_COST_EUR = 1.20
DISCOUNT_PCT = 10
# The credit an apology carries, paid on an order. Not a voucher: `voucher_eur` stays 0, so the
# evidence of apologies (given where there was an issue) is not read as evidence of €5 vouchers.
APOLOGY_CREDIT_EUR = 5

RECENCY_BUCKETS = ("0-90d", "90-180d", "180d+")
# What the customer does in 30 days with no action at all, by recency (visit, click | visit, order | click).
BASE_CHAIN = {"0-90d": (0.60, 0.65, 0.50), "90-180d": (0.35, 0.65, 0.50), "180d+": (0.15, 0.65, 0.50)}
# Months of history before a row can be drawn, and the months a 30-day outcome still has to fit in.
MONTHS_BEFORE = 6
CANDIDATE_MONTHS = 10
ACTED_ON_P = {"0-90d": 0.30, "90-180d": 0.90, "180d+": 0.90}


@dataclass
class CustomerAction:
    action_id: str
    customer_id: str                # link → customers.customer_id
    month: str
    # The customer as the shop could read it that month.
    recency_bucket: str             # days since the last order: 0-90d | 90-180d | 180d+
    spend_band: str                 # the customer's average order: low | mid | high
    offer_buyer: str                # the share of their lines bought on offer: mostly | sometimes | rarely
    open_issue: str                 # none | late_delivery | low_rating
    email_history: str              # earlier win-back emails: responded | ignored | never_sent
    tracking_consent: str           # yes | no
    # What the shop did.
    action: str
    discount_pct: str               # a band: decimals only match equal values in Aito
    voucher_eur: str
    cost_eur: float
    # What followed in the next 30 days.
    visited_30d: bool
    clicked_30d: bool
    purchased_7d: bool
    purchased_30d: bool
    spend_30d_eur: float
    net_30d_eur: float              # spend − cost: what the action was worth in that row
    # The action crossed with each context column ("email|responded"). Aito adds
    # evidence column by column, so an action that works in one context and not in
    # another is only visible to it through these.
    action_x_recency_bucket: str = ""
    action_x_spend_band: str = ""
    action_x_offer_buyer: str = ""
    action_x_open_issue: str = ""
    action_x_email_history: str = ""
    action_x_tracking_consent: str = ""


def _band(share: float, edges: tuple[float, float], names: tuple[str, str, str]) -> str:
    return names[0] if share < edges[0] else names[1] if share < edges[1] else names[2]


def _lifts(action: str, voucher_eur: int, ctx: dict) -> tuple[float, float, float]:
    """(visit, click, order) multipliers that this action gives this context."""
    visit = click = order = 1.0
    if not ON["actions"] or action == "none":
        return visit, click, order
    if action == "email":
        visit = 1.3
        if ON["A1"]:
            visit = {"responded": 1.9, "ignored": 1.0, "never_sent": 1.1}[ctx["email_history"]]
        if ON["A5"] and ctx["open_issue"] != "none":
            visit = 1.0
    elif action == "discount":
        order = {"mostly": 2.0, "sometimes": 1.2, "rarely": 1.0}[ctx["offer_buyer"]] if ON["A2"] else 1.4
    elif action == "voucher":
        visit = 1.05
        if ON["A3"] and ctx["recency_bucket"] == "180d+":
            visit = 2.2
        if voucher_eur == 10:
            visit, order = visit * 1.15, order * 1.15
    elif action == "ad":
        consents = ctx["tracking_consent"] == "yes" or not ON["A4"]
        if consents:
            visit, click, order = 1.5, 1.25, 0.95
    elif action == "apology":
        if ON["A5"] and ctx["open_issue"] != "none":
            visit, order = 1.8, 1.6
    return visit, click, order


def _action_weights(ctx: dict) -> list[float]:
    """The shop picks partly by rule and partly at random: every action
    occurs in every context, often enough to learn where it does not work. A shop
    that only ever apologised to unhappy customers could not tell what an apology does to the rest."""
    weights = {"none": 0.25, "email": 0.15, "discount": 0.15, "voucher": 0.15, "ad": 0.15, "apology": 0.15}
    rule = dict(weights)
    if ctx["open_issue"] != "none":
        rule["apology"] *= 4
    if ctx["tracking_consent"] == "no":
        rule["ad"] *= 0.3
    if ctx["email_history"] == "ignored":
        rule["email"] *= 0.5
    if ctx["offer_buyer"] == "mostly":
        rule["discount"] *= 2
    # Half of the choices follow the rule above, half are a randomised test: a shop that
    # only acts where it expects a result cannot learn where an action does nothing.
    total = sum(rule.values())
    weights = {a: 0.5 * weights[a] / sum(weights.values()) + 0.5 * rule[a] / total for a in weights}
    return [weights[a] for a in ACTIONS]


def _typical_order_eur(customer) -> float:
    if customer.total_orders == 0:
        return 40.0
    return min(200.0, max(15.0, customer.total_spent_eur / customer.total_orders))


class _History:
    """A customer's past, read at a month: what the shop could see."""

    def __init__(self, customers, orders, lines, product_states, nps, winback):
        self.order_months: dict[str, list[tuple[int, str]]] = {}
        self.lines_of: dict[str, list] = {}
        self.discounted = {ps["product_state_id"] if isinstance(ps, dict) else ps.product_state_id:
                           (ps["discount_band"] if isinstance(ps, dict) else ps.discount_band) != "none"
                           for ps in product_states}
        for ln in lines:
            self.lines_of.setdefault(ln.order_id, []).append(ln)
        for o in sorted(orders, key=lambda o: (o.month, o.order_id)):
            self.order_months.setdefault(o.customer_id, []).append((o.month, o.order_id))
        self.nps: dict[str, list[tuple[str, str]]] = {}
        for n in nps:
            self.nps.setdefault(n.customer, []).append((n.month, n.nps_group))
        self.winback: dict[str, list[tuple[str, bool]]] = {}
        for w in winback:
            self.winback.setdefault(w.customer_id, []).append((w.sent_month, w.responded))

    def context(self, customer, month: str, month_index: dict[str, int]) -> dict | None:
        """The customer's context at `month`, or None if they had not ordered yet."""
        before = [(m, oid) for m, oid in self.order_months.get(customer.customer_id, []) if m < month]
        if not before:
            return None
        gap_months = month_index[month] - month_index.get(before[-1][0], month_index[month] - 12)
        recency = RECENCY_BUCKETS[0] if gap_months <= 3 else RECENCY_BUCKETS[1] if gap_months <= 6 else RECENCY_BUCKETS[2]
        lines = [ln for _, oid in before for ln in self.lines_of.get(oid, [])]
        on_offer = sum(self.discounted.get(ln.product_state, False) for ln in lines) / max(1, len(lines))
        last_lines = self.lines_of.get(before[-1][1], [])
        if gap_months <= 3 and any(ln.incident for ln in last_lines):
            issue = "late_delivery"
        elif any(m < month and month_index[month] - month_index.get(m, 0) <= 3 and g == "detractor"
                 for m, g in self.nps.get(customer.customer_id, [])):
            issue = "low_rating"
        else:
            issue = "none"
        sends = [responded for m, responded in self.winback.get(customer.customer_id, []) if m < month]
        return {
            "recency_bucket": recency,
            "spend_band": _band(_typical_order_eur(customer), (35.0, 70.0), ("low", "mid", "high")),
            "offer_buyer": _band(on_offer, (0.20, 0.40), ("rarely", "sometimes", "mostly")),
            "open_issue": issue,
            "email_history": "never_sent" if not sends else "responded" if any(sends) else "ignored",
            "tracking_consent": "yes" if customer.consent_behavioural else "no",
        }


def gen_customer_actions(seed: int, customers, orders, lines, product_states, nps, winback,
                         months: list[str], excluded_ids: set[str]) -> list[CustomerAction]:
    """Actions over the months that have history behind them and 30 days of
    outcome after them."""
    month_index = {m: i for i, m in enumerate(months)}
    history = _History(customers, orders, lines, product_states, nps, winback)
    drawable = months[MONTHS_BEFORE:-1]
    rows: list[CustomerAction] = []
    for customer in customers:
        if customer.customer_id in excluded_ids:
            continue
        rng = stream(seed, "customer_actions", customer.customer_id)
        for month in sorted(rng.sample(drawable, CANDIDATE_MONTHS)):
            ctx = history.context(customer, month, month_index)
            # The shop acts more on customers who are drifting away than on those who just ordered.
            if ctx is None or rng.random() > ACTED_ON_P[ctx["recency_bucket"]]:
                continue
            rows.append(_row(rng, customer, month, ctx, len(rows) + 1))
    return rows


@dataclass
class ActionContext:
    """A customer as the shop reads them when it next chooses an action: the
    columns `customer_actions` has, from the same derivation, as of the month
    after the last one with data."""
    customer_id: str                # link → customers.customer_id
    recency_bucket: str
    spend_band: str
    offer_buyer: str
    open_issue: str
    email_history: str
    tracking_consent: str


def gen_action_contexts(customers, orders, lines, product_states, nps, winback, months: list[str]) -> list[ActionContext]:
    """One row per customer who has ordered, read as of the month after `months` ends."""
    next_month = _next_month(months[-1])
    month_index = {m: i for i, m in enumerate([*months, next_month])}
    history = _History(customers, orders, lines, product_states, nps, winback)
    contexts = ((c, history.context(c, next_month, month_index)) for c in customers)
    return [ActionContext(customer_id=c.customer_id, **ctx) for c, ctx in contexts if ctx is not None]


def _next_month(month: str) -> str:
    year, number = map(int, month.split("-"))
    return f"{year + number // 12:04d}-{number % 12 + 1:02d}"


def crossed(action: str, context: dict) -> dict[str, str]:
    return {f"action_x_{field}": f"{action}|{value}" for field, value in context.items()}


def _row(rng, customer, month: str, ctx: dict, number: int) -> CustomerAction:
    action = rng.choices(ACTIONS, weights=_action_weights(ctx))[0]
    voucher_eur = rng.choice((5, 10)) if action == "voucher" else 0
    discount_pct = DISCOUNT_PCT if action == "discount" else 0
    visit_x, click_x, order_x = _lifts(action, voucher_eur, ctx)
    visit_p, click_p, order_p = BASE_CHAIN[ctx["recency_bucket"]]
    if ctx["open_issue"] != "none":
        visit_p *= 0.7                 # an unhappy customer visits less
    visited = rng.random() < min(0.95, visit_p * visit_x)
    clicked = visited and rng.random() < min(0.95, click_p * click_x)
    purchased = clicked and rng.random() < min(0.95, order_p * order_x)
    # An order within the first week or two, most of the time.
    purchased_7d = purchased and rng.random() < 0.55
    spend = round(_typical_order_eur(customer) * math.exp(rng.gauss(0, 0.35)), 2) if purchased else 0.0
    cost = {"none": 0.0, "email": EMAIL_COST_EUR, "ad": AD_COST_EUR,
            "discount": round(spend * DISCOUNT_PCT / 100, 2),
            "voucher": float(voucher_eur) if purchased else 0.0,
            "apology": EMAIL_COST_EUR + (APOLOGY_CREDIT_EUR if purchased else 0.0)}[action]
    return CustomerAction(
        action_id=f"ACT-{number:06d}", customer_id=customer.customer_id, month=month, **ctx, **crossed(action, ctx),
        action=action, discount_pct=str(discount_pct), voucher_eur=str(voucher_eur), cost_eur=round(cost, 2),
        visited_30d=visited, clicked_30d=clicked, purchased_7d=purchased_7d, purchased_30d=purchased,
        spend_30d_eur=spend, net_30d_eur=round(spend - cost, 2))
