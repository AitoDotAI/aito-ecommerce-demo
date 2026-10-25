"""The Shop card's ? popover: the `$why` chain behind a product's probability.

A `_recommend` hit's `$why` is a product of terms (probed 2026-10-25):

    baseP                         how often a showing ends in a purchase, in general
  × relatedPropositionLift …      the `where` (pets, month, cart) on any product
  × hitLinkPropositionLift        the product's features (brand, category, price): products
                                  like it, whatever the situation
  × hitPropositionLift            the product itself in this situation, with the single
                                  conditions inside it as `factors`
  × normalizer (context, exclusiveness)

`process_why` (the other views' reader) flattens every `relatedPropositionLift` it finds and
drops the other terms, which here would list the pets twice and leave the product's own lift
out. This reads the shape as it is, so the popover's chain reconciles: the terms shown
multiply to the probability once the popover adds Aito's normalising constant.
"""

from __future__ import annotations

import json

from src.aito_client import AitoError
from src.why_processor import _flatten_proposition


def shop_why(why: dict, p: float, context: dict) -> dict:
    """The popover payload (frontend `WhyExplanationPayload`) for one `_recommend` hit."""
    base_p: float | None = None
    situation: list[dict] = []
    features: dict | None = None
    itself: dict | None = None
    for factor in why["factors"]:
        kind = factor["type"]
        if kind == "baseP":
            base_p = float(factor["value"])
        elif kind == "relatedPropositionLift":
            situation.append(_entry(factor, context, "Shoppers in this situation, for any product"))
        elif kind == "hitLinkPropositionLift":
            features = {"label": "Products with this one's features (brand, category, price), "
                                 "whatever the situation",
                        "lift": float(factor["value"]), "propositions": [], "highlight": None}
        elif kind == "hitPropositionLift":
            members = [_entry(f, context) for f in factor.get("factors", [])]
            itself = {"label": "This product in your situation: how each part of it lifts this product",
                      "lift": float(factor["value"]), "propositions": [], "highlight": None,
                      "members": members}
        elif kind != "normalizer":
            raise AitoError(f"Unexpected `$why` term {kind!r}: {json.dumps(factor)[:200]}")
    if base_p is None:
        raise AitoError(f"`$why` has no baseP: {json.dumps(why)[:300]}")
    lifts = situation + [e for e in (features, itself) if e is not None]
    return {"base_p": round(base_p, 4), "predicted_value": "purchased", "lifts": lifts,
            "final_p": round(p, 4)}


def _entry(factor: dict, context: dict, label: str | None = None) -> dict:
    propositions = _flatten_proposition(factor["proposition"])
    entry = {"lift": round(float(factor["value"]), 3), "propositions": propositions,
             "highlight": _highlight(propositions, context)}
    if label is not None:
        entry["label"] = label
    return entry


def _highlight(propositions: list[dict], context: dict) -> dict | None:
    """The context's text with the words Aito matched marked, for a text field of the `where`.

    Aito returns no `highlight` on a `_recommend` hit, but the `where` is our own text: the
    cart's category words or the household's pets. The marks are the words the proposition
    names, so what the popover shows is the query, not a guess.
    """
    for field in dict.fromkeys(p["field"] for p in propositions):
        words = _context_words(context.get(field))
        if not words:
            continue
        matched = {p["value"] for p in propositions if p["field"] == field}
        marked = " ".join(f"«{w}»" if w in matched else w for w in words)
        return {"field": field.removeprefix("context."), "marked_text": marked}
    return None


def _context_words(condition: object) -> list[str]:
    """The words of a `{"$match": w}` or `{"$and": [{"$match": w}, …]}` condition."""
    if not isinstance(condition, dict):
        return []
    if "$match" in condition:
        return str(condition["$match"]).split()
    return [w for sub in condition.get("$and", []) for w in _context_words(sub)]
