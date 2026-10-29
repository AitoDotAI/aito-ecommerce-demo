"""Which action brings an at-risk customer back? Retention's choice among several (ADR 0051).

`customer_actions` holds what the shop did for a customer in a month, "none"
included, the customer's context then, and the next 30 days. For each shown
customer and each candidate action:

  1. `_predict purchased_30d` (and `visited_30d`) with the customer's context
     and the action in the `where`: the chance they order, or visit, after it.
     The context is read from `action_contexts`, the same columns.
  2. `_estimate spend_30d_eur` given `purchased_30d: true` for the customer's
     spend band: the order's size if they do.

An action is worth what it adds over doing nothing in the same context:
  (chance after it − chance after none) × order value − what it costs.
Costs are the shop's own arithmetic: an email or an ad costs when sent; a
discount or a voucher costs only on an order, and on every order including
the ones that would have come anyway. The ranking is by that net, so an
action that lifts nothing, or lifts less than it costs, comes out negative
and "no action" is the best choice.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from src.aito_client import AitoClient, AitoError
from src.catalogue_reads import read_all

EMAIL_COST_EUR = 0.50
AD_COST_EUR = 1.20
DISCOUNT_PCT = 10
APOLOGY_CREDIT_EUR = 5
BATCH_SIZE = 50

# The values the table holds. A value it never saw makes Aito answer with the base
# rate and a 200, so a customer with a context outside these fails here instead.
CONTEXT_VOCABULARY = {
    "recency_bucket": {"0-90d", "90-180d", "180d+"},
    "spend_band": {"low", "mid", "high"},
    "offer_buyer": {"rarely", "sometimes", "mostly"},
    "open_issue": {"none", "late_delivery", "low_rating"},
    "email_history": {"never_sent", "ignored", "responded"},
    "tracking_consent": {"yes", "no"},
}


@dataclass(frozen=True)
class Candidate:
    action: str
    label: str
    discount_pct: int = 0
    voucher_eur: int = 0
    credit_eur: int = 0            # an apology's credit: paid on an order, but not a voucher in the data
    sent_cost_eur: float = 0.0     # paid when it goes out

    def cost_on_order(self, order_value_eur: float) -> float:
        return self.voucher_eur + self.credit_eur + order_value_eur * self.discount_pct / 100


CANDIDATES = (
    Candidate("none", "No action"),
    Candidate("email", "Email", sent_cost_eur=EMAIL_COST_EUR),
    Candidate("discount", f"{DISCOUNT_PCT} % discount", discount_pct=DISCOUNT_PCT),
    Candidate("voucher", "€5 voucher", voucher_eur=5),
    Candidate("voucher", "€10 voucher", voucher_eur=10),
    Candidate("ad", "Personalised ad", sent_cost_eur=AD_COST_EUR),
    Candidate("apology", f"Apology and €{APOLOGY_CREDIT_EUR} credit", credit_eur=APOLOGY_CREDIT_EUR,
              sent_cost_eur=EMAIL_COST_EUR),
)


@dataclass(frozen=True)
class ActionOption:
    action: str
    label: str
    visit_p: float
    purchase_p: float
    purchase_lift_p: float         # purchase_p − the chance after no action
    net_vs_none_eur: float         # what it adds over no action, after its cost
    cost_eur: float                # expected cost: sent cost plus the cost paid on an order


@dataclass(frozen=True)
class RankedActions:
    context: dict
    order_value_eur: float
    options: list[ActionOption]    # best first; "No action" is always among them
    best: str                      # the first option's label


def ranked_actions_for(client: AitoClient, customer_ids: list[str]) -> dict[str, RankedActions]:
    contexts = _contexts(client, customer_ids)
    order_values = _order_values(client, {c["spend_band"] for c in contexts.values()})
    asked = [(cid, cand) for cid in customer_ids for cand in CANDIDATES]
    answers: list[dict] = []
    for start in range(0, len(asked), BATCH_SIZE):
        chunk = asked[start:start + BATCH_SIZE]
        answers += client.batch([_predict_body(contexts[cid], cand, outcome)
                                 for cid, cand in chunk for outcome in ("purchased_30d", "visited_30d")])
    by_pair = {pair: (_true_p(answers[2 * i], pair, "purchased_30d"), _true_p(answers[2 * i + 1], pair, "visited_30d"))
               for i, pair in enumerate((cid, cand.label) for cid, cand in asked)}
    return {cid: _ranked(contexts[cid], order_values[contexts[cid]["spend_band"]], by_pair, cid) for cid in customer_ids}


def _contexts(client: AitoClient, customer_ids: list[str]) -> dict[str, dict]:
    rows = read_all(client, "action_contexts", where={"customer_id": {"$or": customer_ids}})
    contexts = {r["customer_id"]: {k: r[k] for k in CONTEXT_VOCABULARY} for r in rows}
    for cid in customer_ids:
        if cid not in contexts:
            raise AitoError(f"No action_contexts row for customer {cid}: the table holds one per customer who has ordered")
        for field, allowed in CONTEXT_VOCABULARY.items():
            if contexts[cid][field] not in allowed:
                raise AitoError(f"Customer {cid} has {field}={contexts[cid][field]!r}; the actions were recorded with {sorted(allowed)}")
    return contexts


def _order_values(client: AitoClient, bands: set[str]) -> dict[str, float]:
    def one(band: str) -> float:
        res = client.estimate("customer_actions", where={"spend_band": band, "purchased_30d": True},
                              estimate_field="spend_30d_eur", with_why=False)
        if res.get("estimate") is None:
            raise AitoError(f"_estimate spend_30d_eur returned no estimate for spend band {band}: {res}")
        return max(0.0, float(res["estimate"]))

    with ThreadPoolExecutor(max_workers=3) as pool:
        return dict(zip(sorted(bands), pool.map(one, sorted(bands))))


def _predict_body(context: dict, cand: Candidate, outcome: str) -> dict:
    crossed = {f"action_x_{field}": f"{cand.action}|{value}" for field, value in context.items()}
    where = {**context, **crossed, "action": cand.action,
             "discount_pct": str(cand.discount_pct), "voucher_eur": str(cand.voucher_eur)}
    return {"from": "customer_actions", "where": where, "predict": outcome, "limit": 2, "select": ["$p", "feature"]}


def _true_p(answer: dict, pair: tuple[str, str], outcome: str) -> float:
    hit = next((h for h in answer["hits"] if h["feature"] is True), None)
    if hit is None:
        raise AitoError(f"_predict {outcome} for customer {pair[0]} × {pair[1]} has no true hit: {answer}")
    return float(hit["$p"])


def _ranked(context: dict, order_value: float, by_pair: dict, customer_id: str) -> RankedActions:
    none_p = by_pair[(customer_id, "No action")][0]
    options = []
    for cand in CANDIDATES:
        purchase_p, visit_p = by_pair[(customer_id, cand.label)]
        cost = cand.sent_cost_eur + purchase_p * cand.cost_on_order(order_value)
        options.append(ActionOption(
            action=cand.action, label=cand.label, visit_p=round(visit_p, 3), purchase_p=round(purchase_p, 3),
            purchase_lift_p=round(purchase_p - none_p, 3),
            net_vs_none_eur=round((purchase_p - none_p) * order_value - cost, 2), cost_eur=round(cost, 2)))
    options.sort(key=lambda o: -o.net_vs_none_eur)
    return RankedActions(context=context, order_value_eur=round(order_value, 2), options=options, best=options[0].label)
