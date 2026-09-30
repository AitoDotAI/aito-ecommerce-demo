#!/usr/bin/env python3
"""Do the Evaluation page's accuracies survive a grouped hold-out? Read-only.

    PYTHONPATH=. python scripts/evaluation_holdouts.py

The page's `_evaluate` holds out random ROWS. That leaks when rows come in
groups sharing the answer: a product's size variants share its pet type
and diet, and a customer's order lines share their segment. Each model is
re-scored with `_predict` over a nested `from` that removes the whole group,
next to the row-held-out and pooled versions. Design and decision rule:
docs/verification/evaluation-holdouts.md (pre-registered before the runs).

Every arm goes through a nested `from` (pooled uses a scope that excludes
nothing), checked against a plain `from`, so any effect of the mechanism
itself shows up in the control rather than in the comparison.
"""
from __future__ import annotations

import collections
import random
import re
from concurrent.futures import ThreadPoolExecutor

from src.aito_client import AitoClient
from src.config import load_config

PASS_MARGIN = 0.10   # the Evaluation page's pass threshold over the baseline


def family(name: str) -> str:
    """A product's family: its name without the trailing size ("2kg")."""
    return re.sub(r"\s+\d+(\.\d+)?(g|kg)$", "", name)


def rows(client: AitoClient, table: str) -> list[dict]:
    """Every row of `table`, read from Aito (not the fixtures), so the
    evidence always matches the data the page is scored on."""
    out, offset = [], 0
    while True:
        hits = client.search(table, limit=5000, offset=offset)["hits"]
        out += hits
        if len(hits) < 5000:
            return out
        offset += 5000


def top(client: AitoClient, table: str, scope: dict | None, where: dict, field: str):
    source = {"from": table, "where": scope} if scope is not None else table
    hits = client._request("POST", "/_predict", json={
        "from": source, "where": where, "predict": field, "limit": 1})["hits"]
    return hits[0].get("feature", hits[0].get("$value")) if hits else None


def paired_ci(a: list[int], b: list[int], n_boot: int = 2000) -> tuple[float, float, float]:
    rng = random.Random(0)
    n = len(a)
    diffs = sorted(sum(b[i] - a[i] for i in (rng.randrange(n) for _ in range(n))) / n
                   for _ in range(n_boot))
    return (sum(b) - sum(a)) / n, diffs[int(0.025 * n_boot)], diffs[int(0.975 * n_boot) - 1]


def run(name, items, arms, truth, baseline, grouped_label):
    with ThreadPoolExecutor(max_workers=6) as pool:
        hits = {arm: [int(p == truth(i)) for p, i in zip(pool.map(f, items), items)]
                for arm, f in arms.items()}
    acc = {arm: sum(v) / len(items) for arm, v in hits.items()}
    d, lo, hi = paired_ci(hits["row held out"], hits[grouped_label])
    verdict = "pass" if acc[grouped_label] - baseline >= PASS_MARGIN else "FAIL"
    print(f"\n{name} (n={len(items)})")
    for arm, value in acc.items():
        print(f"  {arm:24} {value:.3f}")
    print(f"  {grouped_label} − row held out: {d:+.3f}  95% CI [{lo:+.3f}, {hi:+.3f}]")
    print(f"  baseline {baseline:.3f} → {verdict}")


def main() -> None:
    client = AitoClient(load_config())
    products = rows(client, "products")
    families = collections.defaultdict(list)
    for p in products:
        families[family(p["name"])].append(p)

    def product_arms(evidence, field):
        return {
            "plain from":    lambda p: top(client, "products", None, evidence(p), field),
            "pooled":        lambda p: top(client, "products", {"$not": {"sku": "NO-SUCH-SKU"}}, evidence(p), field),
            "row held out":  lambda p: top(client, "products", {"$not": {"sku": p["sku"]}}, evidence(p), field),
            "family held out": lambda p: top(client, "products",
                                             {"$not": {"name": {"$match": family(p["name"])}}}, evidence(p), field),
        }

    def sample_families(keep, n):
        names = sorted(f for f, ps in families.items() if any(keep(p) for p in ps))
        random.Random(0).shuffle(names)
        return [min((p for p in families[f] if keep(p)), key=lambda p: p["sku"]) for f in names[:n]]

    # Pet type from the product name (eval_service `pet_type_from_name`).
    pet_ev = lambda p: {"name": p["name"], "brand": p["brand"]}
    pet_base = collections.Counter(p["pet_type"] for p in products).most_common(1)[0][1] / len(products)
    run("pet_type from name", sample_families(lambda p: True, 150), product_arms(pet_ev, "pet_type"),
        lambda p: p["pet_type"], pet_base, "family held out")

    # Dietary tag (eval_service `dietary_from_name`), products that have one.
    has_diet = lambda p: bool(p.get("dietary"))
    diet_ev = lambda p: {"name": p["name"], "brand": p["brand"], "category": p["category"], "pet_type": p["pet_type"]}
    tagged = [p for p in products if has_diet(p)]
    diet_base = collections.Counter(p["dietary"] for p in tagged).most_common(1)[0][1] / len(tagged)
    run("dietary from attributes", sample_families(has_diet, 150), product_arms(diet_ev, "dietary"),
        lambda p: p["dietary"], diet_base, "family held out")

    # Customer segment from product (eval_service `segment_from_product`).
    customer_of = {o["order_id"]: o["customer_id"] for o in rows(client, "orders")}
    lines = rows(client, "order_lines")
    by_sku = {p["sku"]: p for p in products}
    first_line = {}
    for line in sorted(lines, key=lambda l: l["line_id"]):
        first_line.setdefault(customer_of[line["order_id"]], line)
    customers = sorted(first_line)
    random.Random(0).shuffle(customers)
    seg_items = [first_line[c] for c in customers[:200]]
    seg_ev = lambda l: {"product_sku.pet_type": by_sku[l["product_sku"]]["pet_type"],
                        "product_sku.category": by_sku[l["product_sku"]]["category"]}
    seg_base = collections.Counter(l["customer_segment"] for l in lines).most_common(1)[0][1] / len(lines)
    run("customer_segment from product", seg_items, {
        "plain from":   lambda l: top(client, "order_lines", None, seg_ev(l), "customer_segment"),
        "pooled":       lambda l: top(client, "order_lines", {"$not": {"line_id": "NO-SUCH-LINE"}}, seg_ev(l), "customer_segment"),
        "row held out": lambda l: top(client, "order_lines", {"$not": {"line_id": l["line_id"]}}, seg_ev(l), "customer_segment"),
        "customer held out": lambda l: top(client, "order_lines",
                                           {"$not": {"order_id.customer_id": customer_of[l["order_id"]]}},
                                           seg_ev(l), "customer_segment"),
    }, lambda l: l["customer_segment"], seg_base, "customer held out")


if __name__ == "__main__":
    main()
