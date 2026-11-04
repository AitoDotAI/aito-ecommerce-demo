"""What stands out among poor feedback, counted over the reviews and NPS answers of the chosen customers only.

The same four lists as the stored ones (`scripts/feedback_patterns_prototype.py`, which counts every customer through Aito): themes, products,
products with a theme, and product lines. Here the counts and the chance of luck come from the segment's own rows, so a segment's lists differ from
everyone's. The AND-rules Aito mines (`$patterns`) are only stored for all customers.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

from src.feedback_themes import THEMES, themes_of

MIN_PRODUCTS = 3
MIN_POOR_ROWS = 2   # a product with a theme needs at least two poor rows before it is a candidate
NAME_WORDS = re.compile(r"[A-Za-z][A-Za-z-]+")
GROUPS = {
    "stars": {"title": "Reviews of 1–2 stars", "link": "product_sku"},
    "detractors": {"title": "NPS detractors (score 0–6)", "link": "product_state.product_sku"},
}


def p_upper(k: int, group: int, overall: int, n: int) -> float:
    """The chance that a group of `group` rows drawn at random from `n` rows holds `k` or more of the `overall` rows that have the pattern."""
    lc = lambda a, b: math.lgamma(a + 1) - math.lgamma(b + 1) - math.lgamma(a - b + 1)
    return min(1.0, sum(math.exp(lc(overall, x) + lc(n - overall, group - x) - lc(n, group)) for x in range(k, min(group, overall) + 1)))


def segment_patterns(reviews: list[dict], answers: list[dict], customers: set[str], products: dict[str, dict]) -> dict:
    """The lists for reviews of 1–2 stars and for NPS detractors among `customers`, in the shape of the stored `feedback-patterns.json`."""
    stars = [(r["product_sku"], themes_of(r["text"]), r["rating"] <= 2) for r in reviews if r["customer_id"] in customers]
    detractors = [(a["product_state"].rsplit("-", 2)[0], themes_of(a.get("comment")), a["nps_group"] == "detractor")
                  for a in answers if a["customer"] in customers]
    return {name: {"title": GROUPS[name]["title"], "rows": sum(poor for _, _, poor in rows), "of": len(rows),
                   "sections": _sections(rows, GROUPS[name]["link"], products)}
            for name, rows in (("stars", stars), ("detractors", detractors))}


def _sections(rows: list[tuple[str, list[str], bool]], link: str, products: dict[str, dict]) -> dict[str, list[dict]]:
    n, size = len(rows), sum(poor for _, _, poor in rows)

    def row(label: str, k: int, group: int, overall: int, universe: int, clauses: list[dict]) -> dict:
        """`k` of the `group` rows have the pattern; `overall` of the `universe` rows do."""
        share_in, share_all = k / group, overall / universe
        return {"label": label, "k": k, "overall": overall, "clauses": clauses,
                "p": p_upper(k, group, overall, universe), "lift": share_in / share_all if share_all else None, "aito": None, "products": None}

    by_theme, by_theme_poor = Counter(), Counter()
    by_sku, by_sku_poor = Counter(), Counter()
    by_sku_theme, by_sku_theme_poor = Counter(), Counter()
    for sku, themes, poor in rows:
        by_sku[sku] += 1
        by_sku_poor[sku] += poor
        for theme in themes:
            by_theme[theme] += 1
            by_theme_poor[theme] += poor
            by_sku_theme[sku, theme] += 1
            by_sku_theme_poor[sku, theme] += poor

    themes = [row(theme, by_theme_poor[theme], size, by_theme[theme], n, [{"field": "themes", "word": theme}])
              for theme in THEMES if by_theme_poor[theme]]
    named = [row(products[sku]["name"], by_sku_poor[sku], size, by_sku[sku], n, [{"field": link, "value": sku}]) for sku in by_sku if by_sku_poor[sku]]
    # The chance for a product with a theme is that of a product of that size holding so many of the theme's rows, not of the group holding them:
    # a complaint theme occurs almost only in poor feedback, so a large product would otherwise look unusual for its size.
    with_theme = [{**row(f"{products[sku]['name']} AND {theme}", by_sku_theme_poor[sku, theme], by_sku[sku], by_theme[theme], n,
                         [{"field": link, "value": sku}, {"field": "themes", "word": theme}]), "overall": by_sku[sku]}
                  for (sku, theme), poor in by_sku_theme_poor.items() if poor >= MIN_POOR_ROWS]
    return {"themes": _sorted(themes), "products": _sorted(named), "products and themes": _sorted(with_theme),
            "brand and product-name word": _sorted(_lines(rows, size, link, products))}


def _lines(rows: list[tuple[str, list[str], bool]], size: int, link: str, products: dict[str, dict]) -> list[dict]:
    """A brand with a word of the product name, for the words that three or more products of the brand share."""
    skus_of = defaultdict(set)
    for sku, product in products.items():
        for word in set(NAME_WORDS.findall(product["name"])) - set(product["brand"].split()):
            skus_of[product["brand"], word].add(sku)
    n, found = len(rows), []
    for (brand, word), skus in skus_of.items():
        if len(skus) < MIN_PRODUCTS:
            continue
        overall = sum(sku in skus for sku, _, _ in rows)
        k = sum(poor and sku in skus for sku, _, poor in rows)
        if k:
            found.append({"label": f"{brand} · {word}", "k": k, "overall": overall, "p": p_upper(k, size, overall, n), "lift": (k / size) / (overall / n),
                          "clauses": [{"field": f"{link}.brand", "value": brand}, {"field": f"{link}.name", "word": word}], "aito": None, "products": len(skus)})
    return found


def _sorted(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=lambda r: r["p"])
