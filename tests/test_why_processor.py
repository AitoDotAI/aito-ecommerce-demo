"""`$why` tree parsing — the explanation popover's data (WhyPopover).

`_predict ... select [$why]` returns the same explanation tree in two
encodings: v1 (Rep1) wraps proposition values in an operator (`$has`)
and groups conjunctions under `$and`; v2 (Rep2) uses `$match` for text
matches, returns bare values for other fields, and groups under
`$group`. The popover must read either — a parser that understood only
v1 silently dropped every factor's conditions on v2, which is the
demo-effect defect the accounting demo hit (its `$why` degraded to a
bare base rate with no error). These tests pin BOTH encodings so a
future change to one path can't quietly break the other.

Pure functions — no live Aito needed, so they run in `./do test`.
"""

from __future__ import annotations

from src.why_processor import _flatten_proposition, process_why


# ── Proposition flattening: the two API encodings ────────────────────


def test_v1_conjunction_and_has_flattens_to_field_value_pairs():
    """v1: `{$and: [{name: {$has: v}}, ...]}` → one {field, value} each."""
    prop = {"$and": [
        {"name": {"$has": "hill's"}},
        {"name": {"$has": "food"}},
    ]}
    assert _flatten_proposition(prop) == [
        {"field": "name", "value": "hill's"},
        {"field": "name", "value": "food"},
    ]


def test_v2_group_and_match_flattens_to_the_same_pairs():
    """v2: `{$group: [{name: {$match: v}}, ...]}` must flatten to real
    values — not an empty list (which drops the card's conditions) and
    not a stringified `{'$match': ...}` dict (which prints raw JSON in
    the popover). This is the accounting-class regression guard."""
    prop = {"$group": [
        {"name": {"$match": "turkey"}},
        {"name": {"$match": "dog"}},
    ]}
    assert _flatten_proposition(prop) == [
        {"field": "name", "value": "turkey"},
        {"field": "name", "value": "dog"},
    ]


def test_v2_bare_value_flattens():
    """v2 non-text fields return the bare value with no operator wrapper."""
    assert _flatten_proposition({"vendor": "Kesko"}) == [
        {"field": "vendor", "value": "Kesko"},
    ]


def test_single_field_match_flattens():
    """A lone (non-conjunction) v2 `$match` proposition still yields its
    value, not the wrapper dict."""
    assert _flatten_proposition({"name": {"$match": "2kg"}}) == [
        {"field": "name", "value": "2kg"},
    ]


def test_not_propagates_negate_flag():
    """`$not` marks its inner propositions as negated (rendered 'is not')."""
    out = _flatten_proposition({"$not": {"pet_type": {"$has": "cat"}}})
    assert out == [{"field": "pet_type", "value": "cat", "negate": True}]


# ── Full-tree walk: a compound v2 lift keeps its conditions ──────────


def _tree(proposition: dict) -> dict:
    """A minimal `_predict $why` tree with one baseP + one lift."""
    return {"type": "product", "factors": [
        {"type": "baseP", "value": 0.3458},
        {"type": "relatedPropositionLift", "value": 1.48,
         "proposition": proposition},
    ]}


def test_process_why_v2_group_keeps_lift_conditions():
    """The whole reason the parser exists: on v2 a compound lift must
    still carry its 'when field is value' conditions. An empty
    `propositions` here is exactly the silent degradation we guard
    against — the card would show a bare `× 1.48` with no explanation."""
    v2_tree = _tree({"$group": [
        {"name": {"$match": "turkey"}},
        {"name": {"$match": "dog"}},
    ]})
    out = process_why(v2_tree, predicted_value="dry-food", actual_p=0.98)
    assert out is not None
    assert out["base_p"] == 0.3458
    assert len(out["lifts"]) == 1
    props = out["lifts"][0]["propositions"]
    assert props == [
        {"field": "name", "value": "turkey"},
        {"field": "name", "value": "dog"},
    ]


def test_process_why_v1_and_v2_produce_identical_conditions():
    """Same explanation, two encodings, one rendered result — the
    property the compat fix guarantees."""
    v1 = _tree({"$and": [{"name": {"$has": "turkey"}}, {"name": {"$has": "dog"}}]})
    v2 = _tree({"$group": [{"name": {"$match": "turkey"}}, {"name": {"$match": "dog"}}]})
    a = process_why(v1, predicted_value="dry-food", actual_p=0.98)
    b = process_why(v2, predicted_value="dry-food", actual_p=0.98)
    assert a == b


def test_process_why_returns_none_without_base():
    """No baseP in the tree → no explanation (the popover shows nothing
    rather than a misleading partial chain)."""
    tree = {"type": "product", "factors": [
        {"type": "relatedPropositionLift", "value": 1.48,
         "proposition": {"name": {"$has": "turkey"}}},
    ]}
    assert process_why(tree, predicted_value="x", actual_p=0.5) is None
