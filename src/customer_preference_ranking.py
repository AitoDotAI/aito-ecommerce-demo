"""Rank the customers by how much they prefer something, and see how the segments split along it (ADR 0053).

A preference is a share of what a customer bought: the lines on offer, in the cheaper half of the category, in
better-rated products, in one category or of one brand. A customer's lift is their share over everyone's average share.
Customers are ranked by it, split into twenty equal steps (the curve) and five (the quintiles), and for each quintile we
count how many of each segment's customers are in it. The question this answers: how much more do the top fifth prefer
this than the bottom fifth, and which segments are the top fifth made of.

Where the bottom fifth buys none of it (most categories), the top-to-bottom ratio is undefined and is left out; the
top fifth over the average is always given.
"""

from __future__ import annotations

from collections import Counter, defaultdict

BINS = 20
GROUPS = 5
MIN_LINES = 3                    # lines (of that pet, for a category) a customer needs to be ranked
MIN_CUSTOMERS = 100              # ranked customers a preference needs
TOP_CATEGORIES = 8
TOP_BRANDS = 6


def line_features(product: dict, state: dict, median_list_price: float, mean_rating: float | None) -> dict[str, bool]:
    """What one purchased line says: on offer, the cheaper half (by list price), better rated, which category and brand."""
    return {
        "offer": bool(state["on_offer"]),
        "cheaper": state["list_price_eur"] < median_list_price,
        "rated": bool(product.get("avg_rating")) and mean_rating is not None and product["avg_rating"] > mean_rating,
        f"category:{product['category']} ({product['pet_type']})": True,
        f"brand:{product['brand']}": True,
    }


def scores(lines_by_customer: dict[str, list[dict]], profiled: set[str]) -> dict[str, dict[str, float]]:
    """variable -> customer -> share. `lines_by_customer[c]` holds, per line, its `features` (see `line_features`) and its `pet`."""
    shares: dict[str, dict[str, float]] = defaultdict(dict)
    buyers: Counter = Counter()
    for customer in profiled & set(lines_by_customer):
        lines = lines_by_customer[customer]
        for feature in {f for ln in lines for f in ln["features"] if f not in ("offer", "cheaper", "rated")}:
            buyers[feature] += 1
        if len(lines) >= MIN_LINES:
            for var in ("offer", "cheaper", "rated"):
                shares[var][customer] = sum(ln["features"][var] for ln in lines) / len(lines)
    categories = [f for f, _ in buyers.most_common() if f.startswith("category:")][:TOP_CATEGORIES]
    brands = [f for f, _ in buyers.most_common() if f.startswith("brand:")][:TOP_BRANDS]
    for customer in profiled & set(lines_by_customer):
        lines = lines_by_customer[customer]
        for var in categories:
            pet = var.rsplit("(", 1)[1].rstrip(")")
            own = [ln for ln in lines if ln["pet"] == pet]
            if len(own) >= MIN_LINES:
                shares[var][customer] = sum(var in ln["features"] for ln in own) / len(own)
        if len(lines) >= MIN_LINES:
            for var in brands:
                shares[var][customer] = sum(var in ln["features"] for ln in lines) / len(lines)
    return {var: s for var, s in shares.items() if len(s) >= MIN_CUSTOMERS}


def ranking(shares: dict[str, float], segments_of: dict[str, list[str]], segment_keys: list[str]) -> dict:
    """Rank customers by share (highest first), then the curve, the quintiles and the segment split of each quintile."""
    ranked = sorted(shares, key=lambda c: (-shares[c], c))
    mean = sum(shares.values()) / len(shares)
    if mean == 0:
        raise ValueError("Nobody has any of this preference: there is nothing to rank")
    n = len(ranked)

    def part(index: int, parts: int) -> list[str]:
        return ranked[index * n // parts:(index + 1) * n // parts]

    def lift(group: list[str]) -> float:
        return sum(shares[c] for c in group) / len(group) / mean

    quintiles = []
    for g in range(GROUPS):
        group = part(g, GROUPS)
        counts = Counter(k for c in group for k in segments_of.get(c, ()))
        quintiles.append({"customers": len(group), "lift": round(lift(group), 3), "mean_share": round(sum(shares[c] for c in group) / len(group), 4),
                          "segment_share": {k: round(counts[k] / len(group), 3) for k in segment_keys}})
    bottom = sum(shares[c] for c in part(GROUPS - 1, GROUPS)) / len(part(GROUPS - 1, GROUPS))
    top = quintiles[0]["mean_share"]
    return {"customers": n, "mean_share": round(mean, 4), "curve": [round(lift(part(b, BINS)), 3) for b in range(BINS)],
            "quintiles": quintiles, "top_over_average": round(top / mean, 2),
            "top_over_bottom": round(top / bottom, 1) if bottom > 0 else None}


_LABELS = {"offer": "Lines bought on offer", "cheaper": "Lines in the cheaper half of their category",
           "rated": "Lines in better-rated products than their category's average"}


def label(variable: str) -> str:
    return _LABELS.get(variable) or variable.replace("category:", "Category: ").replace("brand:", "Brand: ")
