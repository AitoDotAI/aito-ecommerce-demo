"""Which sessions the personalised-search benchmark scores, and its ceiling (ADR 0037 §3).

Offline: read from the fixtures and the regenerated `data/impressions.json`
(skipped when that gitignored file is missing). The numbers are the ones
the pre-registration states, so a regenerated dataset that moves them
fails here before a run would quietly score a different set.
"""

from __future__ import annotations

import json
from collections import Counter

import pytest

from src.personalised_search.generator_ranking import generator_ranking, generator_weight
from src.personalised_search.sessions import DATA, scored_sessions


# The counts below were pre-registered on release 1's data (env `observable`).
REGISTERED_ON = "observable"


@pytest.fixture(scope="module")
def sessions():
    if not (DATA / "impressions.json").exists():
        pytest.skip("data/impressions.json missing: run ./do generate-fixtures")
    release = json.loads((DATA / "release-env.json").read_text(encoding="utf-8"))["env"]
    if release != REGISTERED_ON:
        pytest.skip(f"the benchmark's counts are registered on env {REGISTERED_ON}, the data is {release}'s: "
                    f"re-register them for this release")
    return scored_sessions()


def test_scored_sessions_are_the_search_sessions_with_a_purchase_less_the_personas(sessions):
    assert len(sessions) == 3030
    assert not {s.customer for s in sessions} & {"CUST-00001", "CUST-00002", "CUST-00003"}
    assert all(s.bought and s.query for s in sessions)


def test_history_slices_hold_the_preregistered_counts(sessions):
    assert Counter(s.slice for s in sessions) == {"0": 814, "1-2": 1197, "3-5": 638, "6+": 381}


def test_the_ceiling_ranks_a_pool_that_holds_every_product_bought(sessions):
    # The generator showed products only from the phrase's pool, so a purchase
    # outside it would mean the ranking reads a different pool than it drew from.
    outside = [s.session_id for s in sessions[:500] if not s.bought <= set(generator_ranking(s))]
    assert outside == []


def test_the_generator_weight_favours_a_loyal_shoppers_favourite_brand():
    from types import SimpleNamespace

    shopper = SimpleNamespace(segment="dog_owner", pet_size="medium", diet_rule=None, lifestyle="mid",
                              health_focus="medium", treat_affinity="medium", brand_loyalty="loyal",
                              favorite_brands=("Acana",))
    product = dict(pet_type="dog", category="treats", name="Dog Treats", dietary=None, weight_kg=None)
    favourite = generator_weight(SimpleNamespace(brand="Acana", **product), shopper)
    other = generator_weight(SimpleNamespace(brand="Other", **product), shopper)
    assert favourite == pytest.approx(6.0 * other)
