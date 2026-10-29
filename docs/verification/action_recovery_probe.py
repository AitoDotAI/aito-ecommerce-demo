"""Does Aito recover the action the generator planted as best? (ADR 0051, slice 1)

Run from the repo root, read-only, on the env that holds `customer_actions`:

    AITO_ENV=release3b PYTHONPATH=. uv run python docs/verification/action_recovery_probe.py

For 300 random customers it ranks the candidate actions as Retention does
(`src.retention_actions`) and compares the pick with the best action by the
generator's own expected net (`data.customer_actions._lifts`, the planted
effects), and the cost of each policy: Aito's pick, always email, never act.
The report that quotes its output is `action-recovery.md`.
"""

import random

from src.aito_client import AitoClient
from src.config import load_config
from src.retention_actions import CANDIDATES, ranked_actions_for
from data.customer_actions import BASE_CHAIN, _lifts

client = AitoClient(load_config())
rows = client.search("action_contexts", limit=3000)["hits"]
random.Random(1).shuffle(rows)
sample = rows[:300]
ids = [r["customer_id"] for r in sample]
ranked = {}
for i in range(0, len(ids), 20):
    ranked.update(ranked_actions_for(client, ids[i:i + 20]))


def true_net(ctx, cand, v):
    vis, clk, od = _lifts(cand.action, cand.voucher_eur, ctx)
    vp, cp, op = BASE_CHAIN[ctx["recency_bucket"]]
    if ctx["open_issue"] != "none":
        vp *= 0.7
    pb = min(.95, vp * vis) * min(.95, cp * clk) * min(.95, op * od)
    cost = cand.sent_cost_eur + pb * cand.cost_on_order(v)
    return pb * v - cost


by_label = {cd.label: cd for cd in CANDIDATES}
agree = regret = regret_email = regret_none = 0
top_counts = {}
for r in sample:
    ra = ranked[r["customer_id"]]
    ctx, v = ra.context, ra.order_value_eur
    truth = {cd.label: true_net(ctx, cd, v) for cd in CANDIDATES}
    best_truth = max(truth, key=truth.get)
    chosen = ra.best
    agree += chosen == best_truth
    regret += truth[best_truth] - truth[chosen]
    regret_email += truth[best_truth] - truth["Email"]
    regret_none += truth[best_truth] - truth["No action"]
    top_counts[chosen] = top_counts.get(chosen, 0) + 1
n = len(sample)
print("n", n, "agree with generator's best", agree / n)
print("mean regret EUR  aito", regret / n, " always-email", regret_email / n, " never act", regret_none / n)
print("aito picks", top_counts)
