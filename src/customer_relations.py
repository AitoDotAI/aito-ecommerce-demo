"""How a selection of customers relates to the other variables, and what it buys over-proportionally (ADR 0053).

Both compare the selected customers with the customers outside it, as a difference of shares in points with its
margin (the units are customers, so the margin is valid; lines would cluster by customer). Many values and
hundreds of items are compared, and about one in twenty would pass a 95 % margin by chance, so the margin here is
99.7 % (z = 3). A difference inside its margin is not called a result, and a group too small is left without one.

  - `selection_relations`: of the selected customers, how many more (or fewer) points have each trait value than the rest.
  - `selection_preferences`: of the selected customers, how many more points bought a category, brand or product than the rest.
"""

from __future__ import annotations

from math import sqrt

from src.customer_traits import TOO_FEW

Z = 3.0                        # 99.7 %: hundreds of comparisons are made
MIN_GROUP = 30                 # customers a group needs before a difference is shown
MIN_BUYERS = 5                 # customers in the segment who bought the item, before it is listed
TOP_LISTED = 6
# How a customer shops, and which pets they buy for. Diet tags are left out: a diet belongs to a kind of pet, so
# "buys indoor food" and "has a cat" would show a relation that is only the product catalogue.
RELATION_TRAITS = ("offer", "price", "rating", "margin", "pets")
BEHAVIOUR_TRAITS = ("offer", "price", "rating", "margin")
PET_GROUPS = ("dog", "cat")     # the two with enough customers; preferences are compared within one pet group


def memberships(profile: dict) -> set[tuple[str, str]]:
    """The (trait, value) pairs a profiled customer is in; a trait they have too few purchases for is left out."""
    out = set()
    for trait in RELATION_TRAITS:
        values = profile[trait] if trait == "pets" else [profile[trait]]
        out |= {(trait, v) for v in values if v != TOO_FEW}
    return out


def share_difference(in_hits: int, in_n: int, out_hits: int, out_n: int) -> tuple[float, float]:
    """Points difference of the two shares, and its margin at `Z` (normal approximation for two shares)."""
    p, q = in_hits / in_n, out_hits / out_n
    return round((p - q) * 100, 1), round(Z * sqrt(p * (1 - p) / in_n + q * (1 - q) / out_n) * 100, 1)


def _over_bought(kind: str, inside: list[str], outside: list[str], bought: dict, pet: str) -> list[dict]:
    counts_in: dict[str, int] = {}
    counts_out: dict[str, int] = {}
    for group, counts in ((inside, counts_in), (outside, counts_out)):
        for cid in group:
            for item in bought[cid][pet][kind]:
                counts[item] = counts.get(item, 0) + 1
    rows = []
    for item, hits in counts_in.items():
        if hits < MIN_BUYERS:
            continue
        points, margin = share_difference(hits, len(inside), counts_out.get(item, 0), len(outside))
        rows.append({"item": item, "buyers": hits, "share": round(hits / len(inside), 3),
                     "share_others": round(counts_out.get(item, 0) / len(outside), 3),
                     "points": points, "margin_points": margin, "clear": points > margin})
    return sorted(rows, key=lambda r: (not r["clear"], -r["points"]))[:TOP_LISTED]


def selection_relations(members: dict[str, set[tuple[str, str]]], inside: set[str], skip_traits: set[str]) -> list[dict]:
    """How a selection of customers relates to every trait value outside the traits it is made of: of those inside,
    how many more (or fewer) points have it than the profiled customers outside. `members` is `memberships` per profiled customer."""
    outside = [cid for cid in members if cid not in inside]
    if len(inside) < MIN_GROUP or len(outside) < MIN_GROUP:
        return []
    values = sorted({m for ms in members.values() for m in ms if m[0] not in skip_traits})
    out = []
    for trait, value in values:
        hits_in = sum((trait, value) in members[cid] for cid in inside)
        hits_out = sum((trait, value) in members[cid] for cid in outside)
        points, margin = share_difference(hits_in, len(inside), hits_out, len(outside))
        out.append({"then": {"trait": trait, "value": value}, "customers_with": len(inside), "share_with": round(hits_in / len(inside), 3),
                    "share_without": round(hits_out / len(outside), 3), "points": points, "margin_points": margin, "clear": abs(points) > margin})
    return sorted(out, key=lambda r: (not r["clear"], -abs(r["points"])))


def selection_preferences(inside: set[str], pets_of: dict[str, set[str]], bought: dict[str, dict[str, dict[str, list[str]]]]) -> dict[str, dict]:
    """What a selection buys over-proportionally, per pet group, against the other customers who buy for the same pet."""
    out = {}
    for pet in PET_GROUPS:
        group = [cid for cid, pets in pets_of.items() if pet in pets]
        mine = [cid for cid in group if cid in inside]
        others = [cid for cid in group if cid not in inside]
        if len(mine) < MIN_GROUP or len(others) < MIN_GROUP:
            continue
        entry = {"pet": pet, "customers": len(mine), "others": len(others)}
        for kind in ("categories", "brands", "products"):
            entry[kind] = _over_bought(kind, mine, others, bought, pet)
        out[pet] = entry
    return out
