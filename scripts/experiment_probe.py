#!/usr/bin/env python3
"""Can Aito choose a product's variant per person, by expected profit? (docs/verification/experiments-prereg.md)

    PYTHONPATH=. uv run python scripts/experiment_probe.py                              # dry run: the data and the oracle numbers, no Aito
    AITO_ENV=experiments-probe PYTHONPATH=. uv run python scripts/experiment_probe.py --apply      # loads the training showings
    AITO_ENV=experiments-probe PYTHONPATH=. uv run python scripts/experiment_probe.py --evaluate   # reads, scores the policies

The env is a branch of master (`./do env-new experiments-probe --apply`); the four `xp_` tables are its own, master's tables are not touched.
"""
from __future__ import annotations

import json
import random
import statistics
import sys
from pathlib import Path

from scripts.experiment_probe_data import (ARMS, TRAIT, HELD_OUT, SESSIONS, Shopper, Product, chance, make_products, make_shoppers, make_showings,
                                           leans, observed_winner, oracle_numbers, profit)
from src.aito_client import AitoClient
from src.config import load_config
from src.data_loader import create_schema, delete_table, optimize_table, upload_data

ENV = "experiments-probe"
SEED = 7
PAIRS = 1200            # held-out (shopper, product) pairs scored through Aito
BATCH = 100
SCHEMA = {
    "xp_customers": {"type": "table", "columns": {"customer_id": {"type": "String", "nullable": False}}},
    "xp_products": {"type": "table", "columns": {"sku": {"type": "String", "nullable": False}, "category": {"type": "String", "nullable": False},
                                                 "list_price": {"type": "Decimal", "nullable": False}, "cost": {"type": "Decimal", "nullable": False}}},
    "xp_variants": {"type": "table", "columns": {"variant_id": {"type": "String", "nullable": False},
                                                 "sku": {"type": "String", "nullable": False, "link": "xp_products.sku"},
                                                 "kind": {"type": "String", "nullable": False}, "arm": {"type": "String", "nullable": False},
                                                 "price_eur": {"type": "Decimal", "nullable": False}, "margin_eur": {"type": "Decimal", "nullable": False}}},
    "xp_impressions": {"type": "table", "columns": {"impression_id": {"type": "String", "nullable": False},
                                                    "customer": {"type": "String", "nullable": False, "link": "xp_customers.customer_id"},
                                                    "product_sku": {"type": "String", "nullable": False, "link": "xp_products.sku"},
                                                    "variant": {"type": "String", "nullable": False, "link": "xp_variants.variant_id"},
                                                    "purchased": {"type": "Boolean", "nullable": False},
                                                    # Post-hoc (see the results): how the shopper reacted to this kind of variant, with the arm shown, as one key.
                                                    "lean_arm": {"type": "String", "nullable": False},
                                                    # Diagnostic only: the hidden trait itself, which no shop sees. It bounds what any signal could give.
                                                    "trait_arm": {"type": "String", "nullable": False},
                                                    # Diagnostic: the trait as an observable proxy that is right 70 % of the time and a random level otherwise.
                                                    "proxy_arm": {"type": "String", "nullable": False}}},
}


def proxy_levels(shoppers: list[Shopper], right: float = 0.7) -> dict[tuple[str, str], str]:
    """A signal a shop could observe about each trait: the true level with probability `right`, otherwise a level drawn at random."""
    rng = random.Random(SEED + 3)
    levels = {"discount": ("high", "mid", "low"), "health_focus": ("high", "low"), "visual": ("high", "low")}
    return {(s.shopper_id, kind): (s.traits[TRAIT[kind]] if rng.random() < right else rng.choice(levels[TRAIT[kind]])) for s in shoppers for kind in ARMS}


def world():
    rng = random.Random(SEED)
    shoppers, products = make_shoppers(rng), make_products(rng)
    showings = make_showings(rng, shoppers, products)
    return shoppers, products, showings


def apply(client: AitoClient) -> None:
    if client.env != ENV:
        raise SystemExit(f"Refusing to write: AITO_ENV is {client.env!r}, not {ENV!r}")
    shoppers, products, showings = world()
    train = [r for r in showings if r["session"] < SESSIONS - HELD_OUT]
    lean = leans(train, {p.sku: p for p in products})
    by_product, by_shopper = {p.sku: p for p in products}, {s.shopper_id: s for s in shoppers}
    proxies = proxy_levels(shoppers)
    tables = {
        "xp_customers": [{"customer_id": s.shopper_id} for s in shoppers],
        "xp_products": [{"sku": p.sku, "category": p.category, "list_price": p.list_price, "cost": p.cost} for p in products],
        "xp_variants": [{"variant_id": p.variant_id(arm), "sku": p.sku, "kind": p.kind, "arm": arm, "price_eur": p.price(arm), "margin_eur": p.margin(arm)}
                        for p in products for arm in ARMS[p.kind]],
        "xp_impressions": [{"impression_id": f"I{i:07d}", "customer": r["shopper"], "product_sku": r["sku"], "variant": f"{r['sku']}:{r['arm']}", "purchased": r["purchased"],
                            "lean_arm": f"{lean[r['shopper'], by_product[r['sku']].kind]}|{r['arm']}",
                            "trait_arm": f"{by_shopper[r['shopper']].traits[TRAIT[by_product[r['sku']].kind]]}|{r['arm']}",
                            "proxy_arm": f"{proxies[r['shopper'], by_product[r['sku']].kind]}|{r['arm']}"}
                           for i, r in enumerate(train)],
    }
    for table in reversed(list(SCHEMA)):
        delete_table(client, table)
    for table, schema in SCHEMA.items():
        create_schema(client, table, schema)
        upload_data(client, table, tables[table])
        optimize_table(client, table)


def read_p(hit_list: list[dict], value) -> float:
    """P(purchased = value) from a `_predict` answer; fails loudly if the answer does not say."""
    for hit in hit_list:
        if hit.get("$value") == value:
            return hit["$p"]
    raise AssertionError(f"_predict purchased gave no hit for {value!r}: {hit_list}")


def chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def aito_chances(client: AitoClient, pairs: list[tuple[str, Product]]) -> tuple[list[dict[str, float]], list[dict[str, float]]]:
    """For each (shopper, product): E, `_predict purchased` per arm; R, `_recommend variant` over the product's variants."""
    e_queries = [{"from": "xp_impressions", "where": {"customer": shopper, "variant": product.variant_id(arm)}, "predict": "purchased", "limit": 2}
                 for shopper, product in pairs for arm in ARMS[product.kind]]
    r_queries = [{"from": "xp_impressions", "where": {"customer": shopper, "variant.sku": product.sku}, "recommend": "variant",
                  "goal": {"purchased": True}, "limit": 2} for shopper, product in pairs]
    e_answers = [a for part in chunks(e_queries, BATCH) for a in client.batch(part)]
    r_answers = [a for part in chunks(r_queries, BATCH) for a in client.batch(part)]
    e_out, r_out = [], []
    for i, (_, product) in enumerate(pairs):
        arms = ARMS[product.kind]
        e_out.append({arm: read_p(e_answers[2 * i + k]["hits"], True) for k, arm in enumerate(arms)})
        # A hit names the variant id ("P000:offer"), whose last part is the arm.
        r_out.append({hit["$value"].split(":")[1]: hit["$p"] for hit in r_answers[i]["hits"]})
        assert set(r_out[-1]) == set(arms), f"_recommend variant for {pairs[i][0]} / {product.sku} gave {r_out[-1]}"
    return e_out, r_out


def lean_chances(client: AitoClient, pairs: list[tuple[str, Product]], lean: dict, with_customer: bool, shoppers: dict[str, Shopper] | None = None, proxies: dict | None = None) -> list[dict[str, float]]:
    """Post-hoc: `_predict purchased` where the evidence is the shopper's lean with the arm as one key, the product, and optionally the shopper.
    With `shoppers` the key is built from the hidden trait instead (diagnostic: no shop can observe it); with `proxies`, from a signal that is right 70 % of the time."""
    def where(shopper: str, product: Product, arm: str) -> dict:
        if proxies:
            return {"proxy_arm": f"{proxies[shopper, product.kind]}|{arm}", "product_sku": product.sku}
        if shoppers:
            return {"trait_arm": f"{shoppers[shopper].traits[TRAIT[product.kind]]}|{arm}", "product_sku": product.sku}
        found = {"lean_arm": f"{lean[shopper, product.kind]}|{arm}", "product_sku": product.sku}
        return {**found, "customer": shopper} if with_customer else found
    queries = [{"from": "xp_impressions", "where": where(s, p, arm), "predict": "purchased", "limit": 2} for s, p in pairs for arm in ARMS[p.kind]]
    answers = [a for part in chunks(queries, BATCH) for a in client.batch(part)]
    return [{arm: read_p(answers[2 * i + k]["hits"], True) for k, arm in enumerate(ARMS[p.kind])} for i, (_, p) in enumerate(pairs)]


def evaluate(client: AitoClient) -> dict:
    shoppers, products, showings = world()
    by_sku, by_id = {p.sku: p for p in products}, {s.shopper_id: s for s in shoppers}
    train = [r for r in showings if r["session"] < SESSIONS - HELD_OUT]
    held = [r for r in showings if r["session"] >= SESSIONS - HELD_OUT]
    winner = observed_winner(train, by_sku)
    rng = random.Random(SEED + 1)
    pairs = [(s, by_sku[k]) for s, k in rng.sample(sorted({(r["shopper"], r["sku"]) for r in held}), PAIRS)]
    e, r = aito_chances(client, pairs)
    lean = leans(train, by_sku)
    e2, e3 = lean_chances(client, pairs, lean, False), lean_chances(client, pairs, lean, True)
    e4 = lean_chances(client, pairs, lean, False, by_id)
    e5 = lean_chances(client, pairs, lean, False, None, proxy_levels(shoppers))

    def score(choose) -> list[float]:
        return [profit(by_id[s], p, choose(i, s, p)) for i, (s, p) in enumerate(pairs)]

    best = lambda table: (lambda i, s, p: max(ARMS[p.kind], key=lambda arm: table[i][arm] * p.margin(arm)))
    policies = {"P0 control": score(lambda i, s, p: ARMS[p.kind][0]), "P1 winner": score(lambda i, s, p: winner[p.sku]),
                "P2-E predict": score(best(e)), "P2-R recommend": score(best(r)),
                "P2-E2 lean (post hoc)": score(best(e2)), "P2-E3 lean+customer (post hoc)": score(best(e3)),
                "P2-E4 hidden trait (diagnostic)": score(best(e4)), "P2-E5 70 % proxy (diagnostic)": score(best(e5)),
                "P3 oracle": score(lambda i, s, p: max(ARMS[p.kind], key=lambda arm: profit(by_id[s], p, arm)))}
    per_shopper = lambda values: [[v for (s, _), v in zip(pairs, values) if s == who] for who in sorted({s for s, _ in pairs})]

    def bootstrap(a: list[float], b: list[float]) -> tuple[float, float]:
        """95 % interval of mean(a) - mean(b) over shoppers."""
        pa, pb, brng = per_shopper(a), per_shopper(b), random.Random(SEED + 2)
        diffs = []
        for _ in range(400):
            idx = [brng.randrange(len(pa)) for _ in pa]
            diffs.append(statistics.fmean([v for i in idx for v in pa[i]]) - statistics.fmean([v for i in idx for v in pb[i]]))
        diffs.sort()
        return diffs[10], diffs[389]

    means = {k: statistics.fmean(v) for k, v in policies.items()}
    gap = means["P3 oracle"] - means["P1 winner"]
    out = {"pairs": PAIRS, "profit_per_showing": means}
    for name in ("P2-E predict", "P2-R recommend", "P2-E2 lean (post hoc)", "P2-E3 lean+customer (post hoc)", "P2-E4 hidden trait (diagnostic)", "P2-E5 70 % proxy (diagnostic)"):
        lo, hi = bootstrap(policies[name], policies["P1 winner"])
        out[name] = {"vs_P1_percent": 100 * (means[name] - means["P1 winner"]) / means["P1 winner"], "interval": [lo, hi],
                     "share_of_gap": (means[name] - means["P1 winner"]) / gap if gap else None}
    out["calibration"] = {name: statistics.fmean(abs(table[i][arm] - chance(by_id[s], p, arm)) for i, (s, p) in enumerate(pairs) for arm in ARMS[p.kind])
                          for name, table in (("E", e), ("R", r), ("E2", e2), ("E3", e3), ("E4", e4), ("E5", e5))}
    return out


def main(argv: list[str]) -> int:
    if "--apply" not in argv and "--evaluate" not in argv:
        print(json.dumps(oracle_numbers(SEED), indent=1))
        return 0
    client = AitoClient(load_config())
    if "--apply" in argv:
        apply(client)
    if "--evaluate" in argv:
        result = evaluate(client)
        Path("data/evidence").mkdir(exist_ok=True)
        Path("data/evidence/experiment-probe.json").write_text(json.dumps(result, indent=1) + "\n")
        print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
