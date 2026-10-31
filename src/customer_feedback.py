"""What a segment says: its reviews and NPS answers against the other profiled customers (ADR 0053).

Shares are of customers (a customer who wrote three shipping reviews counts once), so the margins are valid;
reviews cluster by customer and would not be. Only profiled customers are counted: a review or an answer from a
customer who did not consent to behavioural profiling belongs to no segment and to "everyone" neither.
"""

from __future__ import annotations

from src.customer_relations import MIN_GROUP, share_difference

MIN_RESPONDENTS = 30   # NPS answers a group needs before its score is given
ABOUT = {"praise": "Wrote praise", "question": "Asked a question", "quality": "Wrote about quality",
         "shipping": "Wrote about shipping", "fit": "Wrote about fit"}


def feedback_by_segment(reviews: list[dict], answers: list[dict], segments_of: dict[str, list[str]], listed: list[str]) -> dict:
    """{segment key: figures and difference rows}, for "all" and every key in `listed`; `segments_of` maps each profiled customer to its keys."""
    wrote: dict[str, list[dict]] = {}
    for review in reviews:
        if review["customer_id"] in segments_of:
            wrote.setdefault(review["customer_id"], []).append(review)
    group_of = {a["customer"]: a["nps_group"] for a in answers if a["customer"] in segments_of}
    facts = {cid: _facts(wrote.get(cid, []), group_of.get(cid)) for cid in segments_of}
    out = {}
    for key in ["all", *listed]:
        inside = [cid for cid, keys in segments_of.items() if key in keys]
        outside = [cid for cid, keys in segments_of.items() if key not in keys] if key != "all" else []
        out[key] = _figures(inside, outside, facts, wrote)
    return out


def _facts(own: list[dict], group: str | None) -> dict:
    return {"wrote": bool(own), "negative": any(r["sentiment"] == "negative" for r in own),
            "categories": {r["category"] for r in own}, "nps_group": group}


def _figures(inside: list[str], outside: list[str], facts: dict, wrote: dict) -> dict:
    reviews = [r for cid in inside for r in wrote.get(cid, [])]
    nps = _nps([facts[cid]["nps_group"] for cid in inside])
    return {"customers": len(inside), "reviewers": sum(facts[cid]["wrote"] for cid in inside), "reviews": len(reviews),
            "mean_rating": round(sum(r["rating"] for r in reviews) / len(reviews), 2) if reviews else None,
            "nps_respondents": nps[1], "nps": nps[0], "rows": _rows(inside, outside, facts)}


def _nps(groups: list[str | None]) -> tuple[float | None, int]:
    answered = [g for g in groups if g]
    if len(answered) < MIN_RESPONDENTS:
        return None, len(answered)
    return round(100 * (answered.count("promoter") - answered.count("detractor")) / len(answered), 1), len(answered)


def _rows(inside: list[str], outside: list[str], facts: dict) -> list[dict]:
    """Per customer measure: the segment's share, the others' and the difference in points with its 99.7 % margin."""
    measures = [("Wrote a review", lambda f: f["wrote"], None), ("Wrote a negative review", lambda f: f["negative"], None),
                *[(label, lambda f, c=c: c in f["categories"], None) for c, label in ABOUT.items()],
                ("Is a promoter", lambda f: f["nps_group"] == "promoter", "nps_group"),
                ("Is a detractor", lambda f: f["nps_group"] == "detractor", "nps_group")]
    rows = []
    for label, test, only_if in measures:
        mine = [facts[cid] for cid in inside if only_if is None or facts[cid][only_if]]
        others = [facts[cid] for cid in outside if only_if is None or facts[cid][only_if]]
        if len(mine) < MIN_GROUP or (outside and len(others) < MIN_GROUP):
            continue
        share = sum(map(test, mine)) / len(mine)
        row = {"label": label, "base": len(mine), "share": round(share, 3), "share_others": None, "points": None, "margin_points": None, "clear": None}
        if outside:
            points, margin = share_difference(sum(map(test, mine)), len(mine), sum(map(test, others)), len(others))
            row |= {"share_others": round(sum(map(test, others)) / len(others), 3), "points": points, "margin_points": margin, "clear": abs(points) > margin}
        rows.append(row)
    return rows
