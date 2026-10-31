#!/usr/bin/env python3
"""Does a customer's history predict their next basket? ADR 0027's main test.

    PYTHONPATH=. python scripts/next_basket_eval.py              # master (read-only)
    AITO_ENV=lifecycle PYTHONPATH=. python scripts/next_basket_eval.py

For each sampled customer, predict the products of their LAST order from
their earlier orders: `_predict product_sku` over `order_lines`, conditioned
on the customer, from a nested `from` that excludes EVERY sampled customer's last
order (so no answer is in the population, and the model reads exactly the rows the
popularity baseline reads). A hit is any product of the last order in the top 10. Compared, on the same customers, with the household group's 10 most
bought products, and with a control that conditions on a different random
customer. Design: docs/verification/lifecycle-data-prereg.md §2.
"""
from __future__ import annotations

import collections
import random
from concurrent.futures import ThreadPoolExecutor

from src.aito_client import AitoClient
from src.config import load_config

N_CUSTOMERS = 300
TOP_K = 10
# `customers.pets` is nullable: a household that declared no pets has no such key.
NO_DECLARED_PETS = "no declared pets"


def household_group(customer: dict) -> str:
    """The pets a household declared, in a fixed order, or a named group for those who declared none."""
    return " ".join(sorted(customer["pets"].split())) if customer.get("pets") else NO_DECLARED_PETS


def rows(client: AitoClient, table: str) -> list[dict]:
    out, offset = [], 0
    while True:
        hits = client.search(table, limit=5000, offset=offset)["hits"]
        out += hits
        if len(hits) < 5000:
            return out
        offset += 5000


def predicted(client: AitoClient, customer: str, held_out_orders: set[str]) -> list[str]:
    body = {"from": {"from": "order_lines", "where": {"$not": {"order_id": {"$or": sorted(held_out_orders)}}}},
            "where": {"order_id.customer_id": customer},
            "predict": "product_sku", "limit": TOP_K}
    hits = client._request("POST", "/_predict", json=body)["hits"]
    return [h.get("feature", h.get("$value")) for h in hits]


def paired_ci(a: list[int], b: list[int], n_boot: int = 2000) -> tuple[float, float, float]:
    rng = random.Random(0)
    n = len(a)
    diffs = sorted(sum(b[i] - a[i] for i in (rng.randrange(n) for _ in range(n))) / n
                   for _ in range(n_boot))
    return (sum(b) - sum(a)) / n, diffs[int(0.025 * n_boot)], diffs[int(0.975 * n_boot) - 1]


def main() -> None:
    config = load_config()
    client = AitoClient(config)
    orders = rows(client, "orders")
    lines = rows(client, "order_lines")
    # The household group: the pets it declared (ADR 0033), in a fixed order.
    group_of = {c["customer_id"]: household_group(c) for c in rows(client, "customers")}
    customer_of_order = {o["order_id"]: o["customer_id"] for o in orders}

    by_customer: dict[str, list[dict]] = collections.defaultdict(list)
    for o in orders:
        by_customer[o["customer_id"]].append(o)
    lines_by_order: dict[str, list[dict]] = collections.defaultdict(list)
    for line in lines:
        lines_by_order[line["order_id"]].append(line)

    eligible = sorted(c for c, os in by_customer.items() if len(os) >= 3)
    random.Random(0).shuffle(eligible)
    sample = eligible[:N_CUSTOMERS]
    last_order = {c: max(by_customer[c], key=lambda o: (o["month"], o["order_id"]))["order_id"]
                  for c in sample}
    group = {c: group_of[c] for c in sample}

    # Popularity baseline: the group's most bought products, from all lines
    # except the sampled customers' last orders.
    held_out = set(last_order.values())
    counts: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for line in lines:
        if line["order_id"] not in held_out:
            counts[group_of[customer_of_order[line["order_id"]]]][line["product_sku"]] += 1
    popular = {s: [sku for sku, _ in c.most_common(TOP_K)] for s, c in counts.items()}

    rng = random.Random(1)
    stranger = {c: rng.choice([o for o in eligible if o != c]) for c in sample}

    def hit(skus: list[str], customer: str) -> int:
        return int(bool(set(skus) & {l["product_sku"] for l in lines_by_order[last_order[customer]]}))

    # One at a time: each query builds a ~36 000-row population, and six in
    # parallel drew a 502 from the shared instance that also serves the demos.
    with ThreadPoolExecutor(max_workers=1) as pool:
        model = list(pool.map(lambda c: hit(predicted(client, c, held_out), c), sample))
        control = list(pool.map(lambda c: hit(predicted(client, stranger[c], held_out), c), sample))
    baseline = [hit(popular[group[c]], c) for c in sample]

    print(f"next basket, env {config.aito_env}, {len(sample)} customers, hit rate @{TOP_K}")
    print(f"  model (own history)      {sum(model) / len(sample):.3f}")
    print(f"  popularity (household)   {sum(baseline) / len(sample):.3f}")
    print(f"  control (other customer) {sum(control) / len(sample):.3f}")
    for label, arm in (("model", model), ("control", control)):
        d, lo, hi = paired_ci(baseline, arm)
        print(f"  {label} − popularity: {d:+.3f}  95% CI [{lo:+.3f}, {hi:+.3f}]")


if __name__ == "__main__":
    main()
