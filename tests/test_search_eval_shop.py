"""The Shop-search arms: what each one asks Aito, and the on-pet check.

The bodies are the contract the local probe must confirm on a real engine; these
tests pin what they say, so a change to an arm is a visible diff.
"""

import pytest

from src.search_eval.arms_shop import (arm_evidence, arm_filter, arm_list, evidence_body, filter_blend_body,
                                       on_pet_share, pets_of, shop_arms)
from src.search_eval.arms_shop import household_violations, personas_told_apart, query_word_misses
from src.search_service import PERSONAS

SAARA = PERSONAS["saara"].customer_id   # declares a dog


class RecordingClient:
    """Answers `search` and `recommend` with fixed hits and remembers what was asked."""

    def __init__(self, search_hits, recommend_hits=()):
        self.search_hits, self.recommend_hits = search_hits, list(recommend_hits)
        self.searches, self.recommends = [], []

    def search(self, table, **kwargs):
        self.searches.append((table, kwargs))
        return {"hits": self.search_hits, "total": len(self.search_hits)}

    def recommend(self, table, where, recommend_field, goal, **kwargs):
        self.recommends.append((table, where, recommend_field, goal, kwargs))
        return {"hits": self.recommend_hits}


def test_pets_of_reads_the_declared_pets_of_a_demo_persona():
    assert pets_of(SAARA) == ["dog"]


def test_pets_of_fails_loudly_for_a_customer_with_no_declared_pets():
    with pytest.raises(ValueError, match="declares no pets"):
        pets_of("CUST-00004")   # Lotta Salonen declares none


def test_filter_blend_filters_to_the_household_and_leaves_the_query_out_of_the_evidence():
    body = filter_blend_body("food", SAARA, 10, query_evidence=False)
    assert body["where"] == {"context.customer": SAARA, "product_sku.pet_type": {"$or": ["dog"]}}
    assert body["get"] == "product_sku"
    p, lift = body["orderBy"]["$multiply"]
    assert "$p" in p and lift["$similarity"] == {"name": "food"}


def test_filter_blend_with_evidence_adds_the_query_as_context_evidence():
    body = filter_blend_body("food", SAARA, 10, query_evidence=True)
    assert body["where"]["context.search_query"] == "food"
    assert body["where"]["product_sku.pet_type"] == {"$or": ["dog"]}


def test_evidence_arm_ranks_by_probability_alone_with_the_query_as_evidence():
    body = evidence_body("treats", SAARA, 10)
    assert body["recommend"] == "product_sku" and "orderBy" not in body
    assert body["where"]["context.search_query"] == "treats"
    assert body["where"]["product_sku.pet_type"] == {"$or": ["dog"]}


def test_list_arm_ranks_the_name_matched_products_by_probability_times_lift():
    # B has the higher P but A the stronger text match: 0.2 * 4 beats 0.5 * 1.2.
    client = RecordingClient([{"sku": "A", "$score": 4.0}, {"sku": "B", "$score": 1.2}, {"sku": "C", "$score": 1.0}],
                             [{"sku": "A", "$p": 0.2}, {"sku": "B", "$p": 0.5}])
    assert arm_list("saara")(client, "food", 10) == ["A", "B"]
    _, where, _, _, kwargs = client.recommends[0]
    assert where["product_sku"] == {"$or": ["A", "B"]}      # C matched no word: not a candidate
    assert kwargs["limit"] == 2


def test_list_arm_returns_nothing_when_no_name_holds_a_query_word():
    client = RecordingClient([{"sku": "A", "$score": 1.0}])
    assert arm_list("saara")(client, "zzzz", 10) == []
    assert client.recommends == []


def test_filter_and_evidence_arms_return_the_skus_in_the_order_aito_gave():
    client = RecordingClient([{"sku": "X"}, {"sku": "Y"}], [{"sku": "Z"}])
    assert arm_filter("saara", query_evidence=False)(client, "food", 5) == ["X", "Y"]
    assert arm_evidence("saara")(client, "food", 5) == ["Z"]


def test_every_persona_gets_all_four_shop_arms():
    arms = shop_arms(("maija", "saara"))
    assert len(arms) == 8
    assert {n.split("[")[0] for n in arms} == {"shop A list", "shop B filter x similarity",
                                              "shop C filter + query as evidence", "shop D filter x similarity + evidence"}


def test_on_pet_share_counts_only_the_households_pet_types():
    pet_type_of = {"d1": "dog", "d2": "dog", "c1": "cat", "f1": "fish"}
    assert on_pet_share(["d1", "c1", "d2", "f1"], ["dog"], pet_type_of) == 0.5
    assert on_pet_share([], ["dog"], pet_type_of) is None


def test_household_violations_count_hits_of_another_pet_in_the_top_k():
    pet_type_of = {"d1": "dog", "c1": "cat", "c2": "cat"}
    assert household_violations(["d1", "c1", "c2"], ["dog"], pet_type_of) == 2
    assert household_violations(["d1", "c1", "c2"], ["dog"], pet_type_of, k=1) == 0


def test_query_word_misses_count_hits_whose_name_holds_no_query_word():
    names = {"a": "Royal Canin Dog Food", "b": "Whiskas Salmon Cat Food", "c": "Chew Rope Toy"}
    assert query_word_misses(["a", "b", "c"], "dog food", names) == 1   # only the rope matches neither word


def test_personas_are_told_apart_only_when_their_top_lists_differ():
    assert personas_told_apart({"maija": ["c1", "c2"], "saara": ["d1", "d2"]})
    assert not personas_told_apart({"maija": ["d1", "d2"], "saara": ["d1", "d2"]})
