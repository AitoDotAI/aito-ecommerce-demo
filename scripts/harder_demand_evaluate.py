"""Aito against 'the same range as last month', slice by slice, on the harder dataset (ADR 0062).

    AITO_ENV=harder-demand uv run python scripts/harder_demand_evaluate.py [FIXTURE_DIR]

FIXTURE_DIR is the directory `DEMAND_DYNAMICS=1 ./do generate-fixtures` wrote (default: data/), from which the slices are read: seasonal ware
(the products whose name says Edition), trending products (the planned rises and falls), and launches (products with a month as "new").
Each test month is scored by a model trained only on the months before it; the score is pooled over the last seven months.
"""
from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from data import demand_dynamics
from src.aito_client import AitoClient
from src.config import load_config
from src.demand_evaluation import TEST_MONTHS, months_up_to

BASE = ("units_last_month_bucket", "season", "category", "product_state.rating_band", "product_state.age")
FEATURE_SETS = {"stars, age, season, category": BASE,
                "+ in season": BASE + ("in_season",),
                "+ trend": BASE + ("trend",),
                "+ months on sale, price": BASE + ("months_on_sale", "price_vs_category"),
                "+ all four": BASE + ("in_season", "trend", "months_on_sale", "price_vs_category")}


def slices(fixtures: Path) -> dict[str, set[str]]:
    products = json.loads((fixtures / "products.json").read_text())
    states = json.loads((fixtures / "product_states.json").read_text())
    months = sorted({s["month"] for s in states})
    launch = {}
    for s in states:
        if s["age"] == "new" and s["month"] > months[0]:
            launch[s["product_sku"]] = min(launch.get(s["product_sku"], s["month"]), s["month"])
    seasonal = {p["sku"] for p in products if "Edition" in p["name"]}
    from data import catalogue_events
    planned = demand_dynamics.plan(42, [SimpleNamespace(**{k: p[k] for k in ("sku", "category", "pet_type", "price_eur")}) for p in products],
                                   months, launch, catalogue_events.DEMO_ANCHORS)
    assert set(planned.seasonal) == seasonal, "the replanned seasonal ware is not the one in the fixtures: the slices would be wrong"
    return {"seasonal ware": seasonal, "trending products": set(planned.trend), "launches": set(launch)}


def main() -> None:
    fixtures = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "data"
    client = AitoClient(replace(load_config(), aito_env="harder-demand"))
    sales = json.loads((fixtures / "monthly_sales.json").read_text())
    last = max(r["month"] for r in sales)
    tests = months_up_to(last, TEST_MONTHS)
    for name, skus in slices(fixtures).items():
        in_slice = lambda m: {"$and": [{"month": m}, {"$or": [{"product_sku": s} for s in sorted(skus)]}]}
        rows = [r for r in sales if r["month"] in tests and r["product_sku"] in skus]
        naive = sum(r["units_bucket"] == r["units_last_month_bucket"] for r in rows) / len(rows)
        print(f"\n{name}: {len(skus)} products, {len(rows)} product-months; same range as last month: {naive:.1%}")
        for label, features in FEATURE_SETS.items():
            hit = total = 0
            for month in tests:
                n = sum(1 for r in rows if r["month"] == month)
                if n == 0:
                    continue
                res = client.evaluate(table="monthly_sales", where={f: {"$get": f} for f in features}, predict_field="units_bucket",
                                      train={"month": {"$lt": month}}, test=in_slice(month))
                assert int(res["n"]) == n, f"Aito scored {res['n']} rows for {month}, the fixtures have {n}"
                hit += round(float(res["accuracy"]) * n)
                total += n
            print(f"  Aito, {label:32} {hit / total:.1%}  ({hit / total - naive:+.1%} against the rule)")


if __name__ == "__main__":
    main()
