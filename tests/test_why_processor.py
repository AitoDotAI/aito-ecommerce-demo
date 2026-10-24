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


# ── Groups and order: what the popover lists ─────────────────────────
#
# Aito lists a joint lift for several conditions that hold together AND,
# separately, a small lift for each of those conditions on its own (the
# residual after the joint). Shown as separate lines they look like copies of one
# row (the Product filling popover had ten). So a group is ONE row whose lift is
# joint × its members' lifts, which keeps the chain multiplying out, with the parts
# listed inside it; rows are ordered by how far their lift is from 1.


def _lift(value, *propositions):
    proposition = propositions[0] if len(propositions) == 1 else {"$group": list(propositions)}
    return {"type": "relatedPropositionLift", "value": value, "proposition": proposition}


def _why(*lifts):
    return {"type": "product", "factors": [
        {"type": "baseP", "value": 0.38, "proposition": {"pet_type": "dog"}}, *lifts]}


def test_a_group_and_its_residuals_are_one_row_with_the_parts_inside():
    tree = _why(
        _lift(1.011, {"name": {"$match": "Plan"}}),
        _lift(1.329, {"brand": "Hill's"}, {"name": {"$match": "Plan"}}, {"name": {"$match": "Science"}}),
        _lift(1.011, {"name": {"$match": "Science"}}),
        _lift(1.011, {"brand": "Hill's"}),
        _lift(2.606, {"name": {"$match": "Dog"}}),
    )
    out = process_why(tree, predicted_value="dog", actual_p=0.98)
    rows = out["lifts"]
    assert [len(r["propositions"]) for r in rows] == [1, 3]      # the group, then "Dog" is first
    group = next(r for r in rows if len(r["propositions"]) == 3)
    assert group["joint_lift"] == 1.329
    assert group["lift"] == round(1.329 * 1.011 ** 3, 3)           # joint × the three residuals
    # Equal strength, so Aito's order is kept.
    assert [m["propositions"][0]["value"] for m in group["members"]] == ["Plan", "Science", "Hill's"]
    assert all(m["lift"] == 1.011 for m in group["members"])
    assert len(rows) == 2                                            # no residual left as its own row


def test_the_chain_still_multiplies_out_after_grouping():
    """Grouping must not change the product of the lifts, which the popover prints as an equation."""
    singles = [1.011, 1.011, 2.606]   # the two members of the group, and "Dog"
    tree = _why(
        _lift(1.329, {"brand": "Hill's"}, {"name": {"$match": "Plan"}}),
        _lift(1.011, {"brand": "Hill's"}),
        _lift(1.011, {"name": {"$match": "Plan"}}),
        _lift(2.606, {"name": {"$match": "Dog"}}),
    )
    out = process_why(tree, predicted_value="dog", actual_p=0.98)
    before = 1.329
    for s in singles:
        before *= s
    after = 1.0
    for r in out["lifts"]:
        after *= r["lift"]
    assert abs(before - after) < 0.01


def test_rows_are_ordered_by_how_far_the_lift_is_from_one_either_way():
    """|log lift|: a protective 0.5 (log −0.69) outranks an 1.8 (log 0.59)."""
    tree = _why(
        _lift(1.1, {"name": {"$match": "Food"}}),
        _lift(1.8, {"name": {"$match": "Turkey"}}),
        _lift(0.5, {"name": {"$match": "Sensitive"}}),
        _lift(2.6, {"name": {"$match": "Dog"}}),
    )
    out = process_why(tree, predicted_value="dog", actual_p=0.98)
    assert [r["propositions"][0]["value"] for r in out["lifts"]] == ["Dog", "Sensitive", "Turkey", "Food"]


def test_a_single_condition_that_is_in_two_groups_goes_to_the_larger_one():
    tree = _why(
        _lift(1.2, {"a": "1"}, {"b": "2"}),
        _lift(1.5, {"a": "1"}, {"b": "2"}, {"c": "3"}),
        _lift(1.1, {"b": "2"}),
    )
    out = process_why(tree, predicted_value="x", actual_p=0.5)
    by_size = {len(r["propositions"]): r for r in out["lifts"]}
    assert [m["propositions"][0]["field"] for m in by_size[3]["members"]] == ["b"]
    assert "members" not in by_size[2]


def test_a_single_condition_outside_every_group_stays_its_own_row():
    tree = _why(
        _lift(1.4, {"a": "1"}, {"b": "2"}),
        _lift(1.3, {"z": "9"}),
    )
    out = process_why(tree, predicted_value="x", actual_p=0.5)
    assert sorted(len(r["propositions"]) for r in out["lifts"]) == [1, 2]
    assert all("members" not in r for r in out["lifts"])


def test_an_absence_is_a_member_only_of_a_group_that_also_holds_the_absence():
    """`negate` is part of the identity: 'has Plan' is not the residual of a group that says 'no Plan'."""
    tree = _why(
        _lift(1.4, {"a": "1"}, {"$not": {"name": {"$match": "Plan"}}}),
        _lift(1.1, {"name": {"$match": "Plan"}}),
    )
    out = process_why(tree, predicted_value="x", actual_p=0.5)
    assert len(out["lifts"]) == 2
    assert all("members" not in r for r in out["lifts"])
