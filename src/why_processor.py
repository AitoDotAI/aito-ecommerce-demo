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
             # v2 (Rep2) encodes the same as {"$group": [...]} /
             # {field: {$match: value}} / {field: value} — see
             # _flatten_proposition, which reads either.
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

from src.why_groups import arrange_lifts


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
            "lifts": [                 # strongest first; see src/why_groups.py
                {
                    "lift": float,
                    "propositions": [{"field": str, "value": str}, ...],
                    # only on a group: its own lift, and the single conditions it holds
                    "joint_lift": float,
                    "members": [{"lift": float, "propositions": [...]}, ...],
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
                    # `highlight` is per-factor on `_predict` responses
                    # (despite what some Aito guides say about a
                    # `$why.highlights` array — that shape is the older
                    # response form). When present it's a list of
                    # `{score, field, highlight}` — we surface the
                    # top-scoring entry for the popover to render.
                    "highlight": _pick_highlight(node.get("highlight")),
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
        "lifts": arrange_lifts(lifts),
        "final_p": final_p,
    }


def _flatten_proposition(prop: Any) -> list[dict]:
    """`{field: {$has: value}}` → [{field, value}].
    A conjunction → recursively flattened list.
    `{$not: {...}}` → propagates with a `negate` flag (rendered as 'is not').

    Handles both API encodings, because the same `$why` tree comes back
    shaped differently on v1 and v2 (Rep2) and the popover must read
    either — the accounting demo hit the identical rename and its parser
    now accepts both (see ADR 0025):

      - conjunctions: v1 groups ANDed propositions under `$and`; v2 under
        `$group`.
      - predicates: v1 wraps the value in an operator (`{$has: "Kesko"}`);
        v2 text matches use `{$match: "milk"}`, and v2 non-text fields
        return the bare value (`{vendor: "Kesko"}`).

    Missing either encoding is not a soft failure — it silently drops the
    factor's conditions, so a lift card renders a bare multiplier with no
    "when field is value" text (CLAUDE.md prime directive #2).
    """
    if not isinstance(prop, dict):
        return []
    for conjunction in ("$and", "$group"):
        if conjunction in prop:
            out: list[dict] = []
            for sub in prop[conjunction] or []:
                out.extend(_flatten_proposition(sub))
            return out
    if "$not" in prop:
        inner = _flatten_proposition(prop["$not"])
        for item in inner:
            item["negate"] = True
        return inner
    # Plain `{field: {$has: value}}` / `{field: {$match: value}}` / `{field: value}`
    items: list[dict] = []
    for field, predicate in prop.items():
        if field.startswith("$"):
            continue
        items.append({
            "field": field,
            "value": _stringify(_proposition_value(predicate)),
        })
    return items


def _proposition_value(predicate: Any) -> Any:
    """Pull the value out of a proposition predicate, across encodings.

    v1 wraps it in an operator (`{$has: v}`, `{$is: v}`); v2 text matches
    use `{$match: v}`; v2 non-text fields return the bare value. An
    unrecognised single-operator wrapper still yields its inner value
    rather than stringifying the whole dict into the popover.
    """
    if not isinstance(predicate, dict):
        return predicate
    for op in ("$has", "$is", "$match"):
        if op in predicate:
            return predicate[op]
    operator_values = [v for k, v in predicate.items() if k.startswith("$")]
    if len(operator_values) == 1:
        return operator_values[0]
    return predicate


def _pick_highlight(raw: Any) -> dict | None:
    """Pick the top-scoring highlight from Aito's per-factor `highlight`
    list. Returns `{field, marked_text}` or None.

    Aito returns one entry per matched field; for compound propositions
    (`{$and: [...]}`) the list may have one entry per field. We sort by
    `score` descending and keep the first — that's the field with the
    strongest token match.

    `field` is `$context.<column>` in Aito's response; the prefix is
    stripped here so the frontend sees just the column name.
    """
    if not isinstance(raw, list) or not raw:
        return None
    best = max(raw, key=lambda h: float(h.get("score", 0) or 0))
    field = str(best.get("field", ""))
    if field.startswith("$context."):
        field = field[len("$context."):]
    marked = best.get("highlight")
    if not isinstance(marked, str) or not marked:
        return None
    return {"field": field, "marked_text": marked}


def _stringify(v: Any) -> str:
    """Aito's `$has` values come back as bool / int / float / str.
    The popover renders strings — normalise once here."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return f"{v:g}"   # strips trailing zeros
    return str(v) if v is not None else ""
