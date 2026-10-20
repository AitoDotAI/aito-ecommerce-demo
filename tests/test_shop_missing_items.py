"""Which commonly owned items a household lacks (src/shop_history.py), against a fake Aito."""

import pytest

from src.aito_client import AitoError
from src.shop_history import COMMON_OWNED, missing_items


def owned_hit(token, households):
    return {"related": {"owned": {"$has": token}}, "lift": 1.0,
            "fs": {"fOnCondition": households, "fCondition": 645, "f": households, "n": 12662}}


class FakeAito:
    def __init__(self, hits):
        self.hits = hits
        self.relates: list[tuple] = []

    def relate(self, table, where, relate_field, limit=20):
        self.relates.append((table, where, relate_field))
        return {"hits": self.hits}


def test_the_most_common_items_among_similar_households_that_this_one_lacks():
    fake = FakeAito([owned_hit("small_animal_cage", 645), owned_hit("small_animal_tunnel", 84),
                     owned_hit("small_animal_hideout", 282), owned_hit("small_animal_water_bottle", 645)])

    missing = missing_items(fake, ["small_animal_cage", "small_animal_water_bottle"])

    # Learned from the households that own the same: most common first, owned ones left out.
    assert missing == ["small_animal_hideout", "small_animal_tunnel"]
    assert fake.relates == [("contexts", {"owned": {"$and": [{"$match": "small_animal_cage"},
                                                             {"$match": "small_animal_water_bottle"}]}},
                             "owned")]


def test_at_most_the_common_ones_are_listed():
    fake = FakeAito([owned_hit(f"bird_item{i}", 100 - i) for i in range(12)])

    assert len(missing_items(fake, ["bird_cage"])) == COMMON_OWNED


def test_a_household_owning_nothing_lacks_nothing_and_asks_nothing():
    fake = FakeAito([])

    assert missing_items(fake, []) == [] and fake.relates == []


def test_a_full_page_of_items_fails_loudly():
    with pytest.raises(AitoError, match="full page"):
        missing_items(FakeAito([owned_hit(f"t{i}", 1) for i in range(50)]), ["bird_cage"])
