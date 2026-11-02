"""Prototype for judging, by eye, what pattern search over review and NPS text and products would show (not a feature; no ADR yet).

    uv run python scripts/feedback_patterns_prototype.py

For two groups (reviews of 1–2 stars; NPS detractors) it lists candidate patterns: a product, a brand with a category, a brand with a word of the product name,
and a word of the text. Each row has the counts from `_search` (the rows in the group that have the pattern, the rows with it overall) and a chance from them,
and beside them what Aito's own `_relate` reports for the same pattern, so the two can be compared. Writes data/feedback_patterns.json.
"""
from __future__ import annotations

import collections
import json
import math
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from src.aito_client import AitoClient
from src.aito_compat import related_value
from src.config import load_config

ROOT = Path(__file__).resolve().parent.parent
# `targets` are what `$patterns` mines rules for (it takes one value at a time); `field_sets` are the candidate fields it may combine.
GROUPS = {
    "stars": {"title": "Reviews of 1–2 stars", "table": "reviews", "where": {"rating": {"$lte": 2}}, "link": "product_sku.",
              "targets": [{"rating": 1}, {"rating": 2}],
              "field_sets": [["product_sku.brand", "product_sku.category", "product_sku.pet_type"], ["product_sku.brand", "product_sku.category", "created_at"],
                             ["product_sku", "category"], ["text", "category"]]},
    "detractors": {"title": "NPS detractors (score 0–6)", "table": "nps_responses", "where": {"nps_group": "detractor"}, "link": "product_state.product_sku.",
                   "targets": [{"nps_group": "detractor"}],
                   "field_sets": [["product_state.product_sku.brand", "product_state.product_sku.category", "product_state.product_sku.pet_type"],
                                  ["product_state.product_sku.brand", "product_state.product_sku.category", "month"],
                                  ["product_state.product_sku", "product_state.rating_band"], ["comment", "product_state.rating_band"]]},
}
TEXT_FIELD = {"reviews": "text", "nps_responses": "comment"}
MIN_PRODUCTS = 3


def p_upper(k: int, group: int, overall: int, n: int) -> float:
    """The chance that a group of `group` rows drawn at random from `n` rows holds `k` or more of the `overall` rows that have the pattern."""
    lc = lambda a, b: math.lgamma(a + 1) - math.lgamma(b + 1) - math.lgamma(a - b + 1)
    return min(1.0, sum(math.exp(lc(overall, x) + lc(n - overall, group - x) - lc(n, group)) for x in range(k, min(group, overall) + 1)))


def main() -> None:
    client = AitoClient(load_config())
    products = json.loads((ROOT / "data" / "products.json").read_text())
    pairs: dict[tuple, list[str]] = collections.defaultdict(list)
    for product in products:
        pairs[("category", product["brand"], product["category"])].append(product["sku"])
        for word in set(re.findall(r"[A-Za-z][A-Za-z-]+", product["name"])):
            if word not in product["brand"].split():
                pairs[("word", product["brand"], word)].append(product["sku"])
    pairs = {key: skus for key, skus in pairs.items() if len(skus) >= MIN_PRODUCTS}

    def total(table: str, where: dict) -> int:
        return client.search(table, where=where or None, limit=1)["total"]

    out = {}
    for name, group in GROUPS.items():
        table, where, link = group["table"], group["where"], group["link"]
        n, size = total(table, {}), total(table, where)
        sections: dict[str, list] = {"mined by Aito ($patterns)": [], "products": [], "brand and category": [], "brand and product-name word": [], "words": [], "words mined by Aito ($patterns)": []}

        def row(label: str, k: int, overall: int, aito: dict | None, products_in: int | None = None) -> dict:
            return {"label": label, "k": k, "overall": overall, "p": p_upper(k, size, overall, n) if overall else 1.0,
                    "lift": (k / size) / (overall / n) if overall else None, "aito": aito, "products": products_in}

        aito_row = lambda hit: {"lift": hit["lift"], "fOnCondition": hit["fs"]["fOnCondition"], "fCondition": hit["fs"]["fCondition"], "f": hit["fs"]["f"], "n": hit["fs"]["n"]}
        for hit in client.relate(table, where, link[:-1], limit=700)["hits"]:
            fs = hit["fs"]
            sections["products"].append(row(related_value(hit, link[:-1]), int(fs["fOnCondition"]), int(fs["f"]), aito_row(hit)))
        for hit in client.relate(table, where, TEXT_FIELD[table], limit=400)["hits"]:
            fs = hit["fs"]
            sections["words"].append(row(related_value(hit, TEXT_FIELD[table]), int(fs["fOnCondition"]), int(fs["f"]), aito_row(hit)))

        def one(item):
            (kind, brand, other), skus = item
            if kind == "category":
                pattern = {f"{link}brand": brand, f"{link}category": other}
                relate = {"$and": [{f"{link}brand": brand}, {f"{link}category": other}]}
            else:
                pattern = {f"{link}brand": brand, f"{link}name": {"$match": other}}
                relate = {"$and": [{f"{link}brand": brand}, {f"{link}name": {"$match": other}}]}
            overall = total(table, pattern)
            if not overall:
                return None
            hits = client.relate(table, where, relate, limit=1)["hits"]
            return kind, row(f"{brand} · {other}", total(table, {**pattern, **where}), overall, aito_row(hits[0]) if hits else None, len(skus))

        with ThreadPoolExecutor(8) as pool:
            for result in pool.map(one, pairs.items()):
                if result:
                    sections["brand and category" if result[0] == "category" else "brand and product-name word"].append(result[1])
        # What `$patterns` itself finds: AND-rules over the candidate fields. Its lift is kept beside exact counts and the chance from them.
        seen = set()
        for target in group["targets"]:
            for fields in group["field_sets"]:
                body = {"from": table, "where": target, "select": ["related", "condition", "lift"], "orderBy": "lift", "limit": 12,
                        "relate": {"$patterns": {"$related": {"relate": fields, "k": 8, "to": target}}}}
                for hit in client._request("POST", "/_query", json=body).get("hits", []):
                    clauses = hit["related"]["$and"]
                    text_clauses = [c for c in clauses if next(iter(c)) in ("text", "comment")]
                    if text_clauses:
                        # A Text field comes back as words (`{"$has": word}`); the exact count is a phrase match on each word.
                        words = [next(iter(c.values()))["$has"] for c in text_clauses]
                        others = {next(iter(c)): next(iter(c.values())) for c in clauses if c not in text_clauses}
                        label = " · ".join(words) + "".join(f" AND {k}={v}" for k, v in others.items())
                        pattern = {"$and": [{next(iter(text_clauses[0])): {"$match": w}} for w in words] + [{k: v} for k, v in others.items()]}
                        overall = total(table, pattern)
                        if label not in seen and overall:
                            seen.add(label)
                            sections["words mined by Aito ($patterns)"].append(row(f"{label}  [→ {next(iter(target))}={next(iter(target.values()))}]",
                                total(table, {"$and": [pattern, target]}), overall, {"lift": hit["lift"]}))
                        continue
                    label = " AND ".join(f"{next(iter(c))}={next(iter(c.values()))}" for c in clauses)
                    if label in seen:
                        continue
                    seen.add(label)
                    pattern = {next(iter(c)): next(iter(c.values())) for c in clauses}
                    overall = total(table, pattern)
                    if overall:
                        sections["mined by Aito ($patterns)"].append(row(f"{label}  [→ {next(iter(target))}={next(iter(target.values()))}]",
                                                                      total(table, {**pattern, **where}), overall, {"lift": hit["lift"]}))
        for rows in sections.values():
            rows.sort(key=lambda r: r["p"])
        out[name] = {"title": group["title"], "rows": size, "of": n, "sections": sections}
        print(name, size, "of", n, {k: len(v) for k, v in sections.items()})
    (ROOT / "data" / "feedback_patterns.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")


if __name__ == "__main__":
    main()
