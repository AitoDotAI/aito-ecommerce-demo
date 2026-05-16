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


def process_estimate_why(
    raw_why: Any,
    estimate_value: float | None,
    *,
    field_label: str = "value",
) -> dict | None:
    """Flatten Aito's `_estimate why` tree into the popover shape.

    Aito's `_estimate` returns a `weightedAverage` of
    `neighborContext` nodes, each with an `adjustments` tree that
    decomposes into:

      - `input.residual`  — k-NN neighbor residual (data-driven)
      - `regression`       — per-feature shift (additive on log scale)
      - `mean centering`   — column-mean baseline

    The K-NN math walks a tree of `sum` / `exponent` / `constant`
    nodes. For the popover we collapse this into a flat list of
    contribution rows:

        {
          "kind": "estimate",
          "estimate": float,
          "field_label": str,
          "components": [
            {"name": "season=spring", "value": 0.07, "type": "regression"},
            {"name": "neighbor residual", "value": -0.41, "type": "residual"},
            {"name": "column mean (log)", "value": 0.39, "type": "mean"},
            ...
          ]
        }

    The popover renders these as "Expected X · base + Δ₁ + Δ₂…".
    Values are on the log scale Aito works in internally; the
    popover converts to "+12 %", "-8 %" deltas for display.
    """
    if not isinstance(raw_why, dict):
        return None

    components: list[dict] = []

    def walk_neighbor_subtree(node: Any) -> None:
        """Walk one neighbor's adjustments tree and collect leaves.

        K-NN `_estimate` returns a `weightedAverage` of ~20-30
        neighbors; each neighbor has its own per-feature regression
        terms and column-mean baseline. Walking the full tree
        collects N × (1 residual + N_features regressions + 1 mean)
        leaves — too noisy for a popover.

        Instead we walk only the TOP-weighted neighbor's subtree:
        one representative residual + per-feature shifts + the
        column mean. The reader sees the math for a single
        comparable case, not the K-NN ensemble.
        """
        if not isinstance(node, dict):
            return
        t = node.get("type")
        if t == "regression":
            prop = node.get("proposition", {})
            value = float(node.get("value", 0) or 0)
            if abs(value) < 1e-10:
                return
            field, val = next(iter(prop.items())) if prop else ("", "")
            components.append({
                "name": f"{field}={_stringify(val)}",
                "value": round(value, 4),
                "type": "regression",
            })
            return
        if t == "mean centering":
            value = float(node.get("value", 0) or 0)
            components.append({
                "name": "column mean (log)",
                "value": round(value, 4),
                "type": "mean",
            })
            return
        if t == "input" and node.get("name") == "residual":
            value = float(node.get("value", 0) or 0)
            if abs(value) >= 1e-10:
                components.append({
                    "name": "neighbor residual",
                    "value": round(value, 4),
                    "type": "residual",
                })
            return
        for child_key in ("terms", "factors"):
            for child in node.get(child_key, []) or []:
                walk_neighbor_subtree(child)
        for k in ("value", "base", "power", "adjustments"):
            v = node.get(k)
            if isinstance(v, dict):
                walk_neighbor_subtree(v)

    # Find the top-weighted neighbor under `weightedAverage.components`
    # and walk only its subtree.
    if raw_why.get("type") == "weightedAverage":
        neighbor_components = raw_why.get("components", []) or []
        # Pick the highest-weight neighbor.
        if neighbor_components:
            top = max(neighbor_components, key=lambda c: float(c.get("weight", 0) or 0))
            walk_neighbor_subtree(top.get("value") or top)
    else:
        # Fallback: full walk (handles other `_estimate` model shapes).
        walk_neighbor_subtree(raw_why)

    if estimate_value is None and isinstance(raw_why.get("value"), (int, float)):
        estimate_value = float(raw_why["value"])

    components.sort(key=lambda c: -abs(c["value"]))
    return {
        "kind": "estimate",
        "estimate": round(float(estimate_value), 3) if estimate_value is not None else None,
        "field_label": field_label,
        "components": components[:8],   # top-8 by magnitude
    }


def _stringify(v: Any) -> str:
    """Aito's `$has` values come back as bool / int / float / str.
    The popover renders strings — normalise once here."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return f"{v:g}"   # strips trailing zeros
    return str(v) if v is not None else ""
