"""Parse Aito's `$why` tree into the flat structure WhyPopover renders.

Aito's `_predict ... select [$why]` returns a nested factor tree:

    {
        "type": "product",
        "factors": [
            {"type": "baseP", "value": 0.67, "proposition": {...}},
            {"type": "product", "factors": [
                {"type": "normalizer", ...}, ...
            ]},
            {"type": "relatedPropositionLift",
             "value": 1.39,
             "proposition": {"$and": [...]} or {field: {$has: value}}},
            ...
        ]
    }

The popover only renders **baseP** + **relatedPropositionLift** factors;
normalizers are technical scaling values we drop. Each lift's
proposition is flattened to a list of `{field, value}` pairs the
frontend renders as "When field is value and field is value".

See ADR 0010 (Evaluation) for `_predict` body shape and the
accounting demo's WhyPopover for the canonical visual.
"""

from __future__ import annotations

from typing import Any


def process_why(
    raw_why: Any,
    predicted_value: Any,
    *,
    actual_p: float | None = None,
) -> dict | None:
    """Flatten Aito's `$why` tree.

    Returns a dict matching the frontend's `WhyExplanation` type:

        {
            "base_p": float,           # prior probability of predicted_value
            "predicted_value": Any,    # echoed for the popover title
            "lifts": [
                {
                    "lift": float,
                    "propositions": [{"field": str, "value": str}, ...]
                },
                ...
            ],
            "final_p": float | None,   # base_p × ∏ lift, or None if not computable
        }

    Returns None if the tree is missing or doesn't carry a baseP.
    """
    if not isinstance(raw_why, dict):
        return None

    base_p: float | None = None
    lifts: list[dict] = []

    def walk(node: Any) -> None:
        nonlocal base_p
        if not isinstance(node, dict):
            return
        t = node.get("type")
        if t == "baseP" and base_p is None:
            v = node.get("value")
            if isinstance(v, (int, float)):
                base_p = float(v)
            return
        if t == "relatedPropositionLift":
            v = node.get("value")
            prop = node.get("proposition")
            if isinstance(v, (int, float)) and prop is not None:
                lifts.append({
                    "lift": round(float(v), 3),
                    "propositions": _flatten_proposition(prop),
                })
            return
        # Recurse into product / sum / etc.
        for child in node.get("factors", []) or []:
            walk(child)

    walk(raw_why)

    if base_p is None:
        return None

    # Final probability shown at the end of the chain is Aito's
    # actual `$p` for the predicted class, NOT the literal product
    # base × Π lift. Aito's combined-evidence formula applies
    # additional normalisers (exclusiveness, trueFalseExclusiveness)
    # that the popover doesn't surface — showing the literal product
    # would mismatch the headline number. The accounting demo uses
    # the same convention.
    final_p = round(actual_p, 4) if actual_p is not None else None

    return {
        "base_p": round(base_p, 4),
        "predicted_value": _stringify(predicted_value),
        "lifts": lifts,
        "final_p": final_p,
    }


def _flatten_proposition(prop: Any) -> list[dict]:
    """`{field: {$has: value}}` → [{field, value}].
    `{$and: [...]}` → recursively flattened list.
    `{$not: {...}}` → propagates with a `not_` flag (rendered as 'is not').
    """
    if not isinstance(prop, dict):
        return []
    if "$and" in prop:
        out: list[dict] = []
        for sub in prop["$and"]:
            out.extend(_flatten_proposition(sub))
        return out
    if "$not" in prop:
        inner = _flatten_proposition(prop["$not"])
        for item in inner:
            item["negate"] = True
        return inner
    # Plain `{field: {$has: value}}` or `{field: value}`
    items: list[dict] = []
    for field, predicate in prop.items():
        if field.startswith("$"):
            continue
        if isinstance(predicate, dict):
            value = (
                predicate.get("$has")
                if "$has" in predicate
                else predicate.get("$is")
                if "$is" in predicate
                else predicate
            )
        else:
            value = predicate
        items.append({
            "field": field,
            "value": _stringify(value),
        })
    return items


def _stringify(v: Any) -> str:
    """Aito's `$has` values come back as bool / int / float / str.
    The popover renders strings — normalise once here."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return f"{v:g}"   # strips trailing zeros
    return str(v) if v is not None else ""
