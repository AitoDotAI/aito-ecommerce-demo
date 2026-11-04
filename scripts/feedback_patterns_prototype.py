"""Prototype for judging, by eye, what pattern search over review and NPS text and products would show (not a feature; no ADR yet).

    uv run python scripts/feedback_patterns_prototype.py

For two groups (reviews of 1–2 stars; NPS detractors) it lists candidate patterns: a product, a brand with a category, a brand with a word of the product name,
and a word of the text. Each row has the counts from `_search` (the rows in the group that have the pattern, the rows with it overall) and a chance from them,
and beside them what Aito's own `_relate` reports for the same pattern, so the two can be compared. Writes data/evidence/feedback-patterns.json.
"""
from __future__ import annotations

import collections
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from src.aito_client import AitoClient
from src.aito_compat import related_value
from src.config import load_config
from src.feedback_segment_patterns import p_upper
from src.feedback_themes import THEMES

ROOT = Path(__file__).resolve().parent.parent

# `targets` are what `$patterns` mines rules for (it takes one value at a time); `field_sets` are the candidate fields it may combine.
GROUPS = {
    "stars": {"title": "Reviews of 1–2 stars", "table": "reviews", "where": {"rating": {"$lte": 2}}, "link": "product_sku.",
              "targets": [{"rating": 1}, {"rating": 2}],
              "field_sets": [["product_sku.brand", "product_sku.category", "product_sku.pet_type"], ["product_sku.brand", "product_sku.category", "created_at"],
                             ["product_sku", "category"], ["themes", "product_sku.brand"], ["themes", "created_at"]]},
    "detractors": {"title": "NPS detractors (score 0–6)", "table": "nps_responses", "where": {"nps_group": "detractor"}, "link": "product_state.product_sku.",
                   "targets": [{"nps_group": "detractor"}],
                   "field_sets": [["product_state.product_sku.brand", "product_state.product_sku.category", "product_state.product_sku.pet_type"],
                                  ["product_state.product_sku.brand", "product_state.product_sku.category", "month"],
                                  ["product_state.product_sku", "product_state.rating_band"], ["themes", "product_state.product_sku.category"], ["themes", "product_state.product_sku.brand"], ["themes", "month"], ["themes", "product_state.rating_band"]]},
}
# The text itself is not mined: what a message is about is its theme tags (src/feedback_themes.py), a column Aito can mine like any other.
TEXT_FIELD = {"reviews": "themes", "nps_responses": "themes"}
MIN_PRODUCTS = 3


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
    names = {product["sku"]: product["name"] for product in products}
    # A product is shown by its name: a code (SKU-PT-0202) says nothing to the reader.
    named = lambda label: re.sub(r"(?:product_state\.)?product_sku=(SKU-PT-\d+)", lambda m: f"product={names[m.group(1)]}", label)

    def total(table: str, where: dict) -> int:
        return client.search(table, where=where or None, limit=1)["total"]

    out = {}
    for name, group in GROUPS.items():
        table, where, link = group["table"], group["where"], group["link"]
        n, size = total(table, {}), total(table, where)
        sections: dict[str, list] = {"mined by Aito ($patterns)": [], "products": [], "brand and category": [], "brand and product-name word": [], "themes": [], "themes mined by Aito ($patterns)": [], "products and themes": []}

        def row(label: str, k: int, overall: int, aito: dict | None, products_in: int | None = None, clauses: list | None = None) -> dict:
            # `clauses` say which rows have the pattern, in a form the Customers view can filter its feedback rows by (src/feedback_pattern_filter.py).
            return {"label": label, "k": k, "overall": overall, "clauses": clauses or [], "p": p_upper(k, size, overall, n) if overall else 1.0,
                    "lift": (k / size) / (overall / n) if overall else None, "aito": aito, "products": products_in}

        aito_row = lambda hit: {"lift": hit["lift"], "fOnCondition": hit["fs"]["fOnCondition"], "fCondition": hit["fs"]["fCondition"], "f": hit["fs"]["f"], "n": hit["fs"]["n"]}
        for hit in client.relate(table, where, link[:-1], limit=700)["hits"]:
            fs = hit["fs"]
            sections["products"].append(row(names[related_value(hit, link[:-1])], int(fs["fOnCondition"]), int(fs["f"]), aito_row(hit),
                                            clauses=[{"field": link[:-1], "value": related_value(hit, link[:-1])}]))
        for hit in client.relate(table, where, TEXT_FIELD[table], limit=400)["hits"]:
            fs = hit["fs"]
            sections["themes"].append(row(related_value(hit, TEXT_FIELD[table]), int(fs["fOnCondition"]), int(fs["f"]), aito_row(hit),
                                          clauses=[{"field": TEXT_FIELD[table], "word": related_value(hit, TEXT_FIELD[table])}]))

        # Where a complaint concentrates: for each theme, Aito's `_relate` over the product gives the rows of the product that have the theme (fOnCondition),
        # the rows with the theme (fCondition) and the product's rows (f). The chance is that of a product with that many rows holding so many of the
        # theme's rows, not of the group holding them: a complaint theme only occurs in poor feedback, so a large product would otherwise look unusual for its size.
        for theme in THEMES:
            for hit in client.relate(table, {TEXT_FIELD[table]: {"$match": theme}}, link[:-1], limit=700)["hits"]:
                fs = hit["fs"]
                sku = related_value(hit, link[:-1])
                in_group = total(table, {link[:-1]: sku, TEXT_FIELD[table]: {"$match": theme}, **where})
                if in_group < 2:
                    continue
                share, expected = in_group / fs["f"], fs["fCondition"] / fs["n"]
                sections["products and themes"].append({
                    "label": f"{names[sku]} AND {theme}", "k": in_group, "overall": int(fs["f"]), "clauses": [{"field": link[:-1], "value": sku}, {"field": TEXT_FIELD[table], "word": theme}],
                    "p": p_upper(in_group, int(fs["f"]), int(fs["fCondition"]), int(fs["n"])), "lift": share / expected if expected else None, "aito": {"lift": hit["lift"]}, "products": None})

        def one(item):
            (kind, brand, other), skus = item
            if kind == "category":
                clauses = [{"field": f"{link}brand", "value": brand}, {"field": f"{link}category", "value": other}]
                pattern = {f"{link}brand": brand, f"{link}category": other}
                relate = {"$and": [{f"{link}brand": brand}, {f"{link}category": other}]}
            else:
                clauses = [{"field": f"{link}brand", "value": brand}, {"field": f"{link}name", "word": other}]
                pattern = {f"{link}brand": brand, f"{link}name": {"$match": other}}
                relate = {"$and": [{f"{link}brand": brand}, {f"{link}name": {"$match": other}}]}
            overall = total(table, pattern)
            if not overall:
                return None
            hits = client.relate(table, where, relate, limit=1)["hits"]
            return kind, row(f"{brand} · {other}", total(table, {**pattern, **where}), overall, aito_row(hits[0]) if hits else None, len(skus), clauses)

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
                    text_clauses = [c for c in clauses if next(iter(c)) == "themes" and isinstance(next(iter(c.values())), dict)]
                    # A Text field comes back twice: as words (`{"$has": tag}`) and as the whole value (`{"themes": "late-delivery damaged-packaging"}`).
                    # The whole value is one more way to say the same message, so only the tags are kept; the exact count is a `$match` on each tag.
                    whole_values = [c for c in clauses if next(iter(c)) == "themes" and not isinstance(next(iter(c.values())), dict)]
                    if text_clauses:
                        words = [next(iter(c.values()))["$has"] for c in text_clauses]
                        others = {next(iter(c)): next(iter(c.values())) for c in clauses if c not in text_clauses and c not in whole_values}
                        label = " · ".join(words) + "".join(f" AND {k}={v}" for k, v in others.items())
                        pattern = {"$and": [{next(iter(text_clauses[0])): {"$match": w}} for w in words] + [{k: v} for k, v in others.items()]}
                        overall = total(table, pattern)
                        if label not in seen and overall:
                            seen.add(label)
                            sections["themes mined by Aito ($patterns)"].append(row(f"{label}  [→ {next(iter(target))}={next(iter(target.values()))}]",
                                total(table, {"$and": [pattern, target]}), overall, {"lift": hit["lift"]},
                                clauses=[{"field": next(iter(text_clauses[0])), "word": w} for w in words] + [{"field": f, "value": v} for f, v in others.items()]
                                        + ([{"field": "rating", "value": target["rating"]}] if "rating" in target else [])))   # k counts this one rating, so the rows do
                        continue
                    label = " AND ".join(f"{next(iter(c))}={next(iter(c.values()))}" for c in clauses)
                    if label in seen:
                        continue
                    seen.add(label)
                    pattern = {next(iter(c)): next(iter(c.values())) for c in clauses}
                    overall = total(table, pattern)
                    if overall:
                        sections["mined by Aito ($patterns)"].append(row(f"{label}  [→ {next(iter(target))}={next(iter(target.values()))}]",
                                                                      total(table, {**pattern, **where}), overall, {"lift": hit["lift"]},
                                                                      clauses=[{"field": f, "value": v} for f, v in pattern.items()]))
        for rows in sections.values():
            for r in rows:
                r["label"] = named(r["label"])
            rows.sort(key=lambda r: r["p"])
        out[name] = {"title": group["title"], "rows": size, "of": n, "sections": sections}
        print(name, size, "of", n, {k: len(v) for k, v in sections.items()})
    (ROOT / "data" / "evidence" / "feedback-patterns.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")


if __name__ == "__main__":
    main()
