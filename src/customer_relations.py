"""How the profile variables relate, and what each segment buys over-proportionally (ADR 0053).

Both compare a group of customers with the customers outside it, as a difference of shares in points with its
margin (the units are customers, so the margin is valid; lines would cluster by customer). Many pairs and
hundreds of items are compared, and about one in twenty would pass a 95 % margin by chance, so the margin here is
99.7 % (z = 3). A difference inside its margin is not called a result, and a group too small is left without one.

  - `relations`: of the customers with trait A, how many more (or fewer) points have trait B than those without A.
  - `preferences`: of a segment's customers, how many more points bought a category, brand or product than the rest.
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
RELATION_TRAITS = ("offer", "price", "rating", "pets")
BEHAVIOUR_TRAITS = ("offer", "price", "rating")
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


def relations(profiles: list[dict]) -> list[dict]:
    """For every ordered pair of trait values (A, B) of different traits: B's share among A against among non-A."""
    members = {p["customer_id"]: memberships(p) for p in profiles if p["profiled"]}
    values = sorted({m for ms in members.values() for m in ms})
    out = []
    for a in values:
        with_a = [ms for ms in members.values() if a in ms]
        without_a = [ms for ms in members.values() if a not in ms]
        if len(with_a) < MIN_GROUP or len(without_a) < MIN_GROUP:
            continue
        for b in values:
            if b[0] == a[0]:
                continue
            hits_in, hits_out = sum(b in ms for ms in with_a), sum(b in ms for ms in without_a)
            points, margin = share_difference(hits_in, len(with_a), hits_out, len(without_a))
            out.append({"if": {"trait": a[0], "value": a[1]}, "then": {"trait": b[0], "value": b[1]},
                        "customers_with": len(with_a), "share_with": round(hits_in / len(with_a), 3),
                        "share_without": round(hits_out / len(without_a), 3),
                        "points": points, "margin_points": margin, "clear": abs(points) > margin})
    return out


def preferences(profiles: list[dict], bought: dict[str, dict[str, dict[str, set[str]]]]) -> dict[str, dict]:
    """`bought[customer][pet][kind]` is what the customer bought for that pet, kind in ("categories", "brands",
    "products"). For each way of shopping and each pet group: the items the segment over-buys, by customers
    reached, against the other customers who buy for the same pet (so a cat owner is not compared with a dog
    owner). Clear ones first."""
    members = {p["customer_id"]: memberships(p) for p in profiles if p["profiled"]}
    pet_of = {p["customer_id"]: set(p["pets"]) for p in profiles if p["profiled"]}
    out = {}
    for pet in PET_GROUPS:
        group = [cid for cid in members if pet in pet_of[cid]]
        for seg in sorted({m for cid in group for m in members[cid] if m[0] in BEHAVIOUR_TRAITS}):
            inside = [cid for cid in group if seg in members[cid]]
            outside = [cid for cid in group if seg not in members[cid]]
            if len(inside) < MIN_GROUP or len(outside) < MIN_GROUP:
                continue
            entry = {"pet": pet, "customers": len(inside), "others": len(outside)}
            for kind in ("categories", "brands", "products"):
                entry[kind] = _over_bought(kind, inside, outside, bought, pet)
            out[f"{seg[0]}:{seg[1]}|{pet}"] = entry
    return out


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
