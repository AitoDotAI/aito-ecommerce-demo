"""ADR 0033: Aito sees only what a shop can observe.

O1 and O2 of docs/verification/observable-data-prereg.md. K1, the kit's
next item, is judged against its null by `./do planted-effects`.
"""

import re

from data.observable import HIDDEN_TRAITS, kit_status
from src.schema import SCHEMAS
from tests.fixture_joins import load

# A column is a copy of a hidden trait if it is named after one, with or
# without the `customer_` prefix the old denormalised copies carried.
HIDDEN = re.compile(rf"^(customer_)?({'|'.join(HIDDEN_TRAITS)})$")


def test_o1_no_table_aito_sees_has_a_hidden_trait_column():
    leaks = [(table, col) for table, schema in SCHEMAS.items() for col in schema["columns"] if HIDDEN.match(col)]
    assert not leaks, leaks


def test_o1_no_fixture_row_carries_a_hidden_trait():
    for table in SCHEMAS:
        rows = load(f"{table}.json")
        leaked = {key for row in rows[:5000] for key in row if HIDDEN.match(key)}
        assert not leaked, (table, leaked)


def test_o2_every_impressions_context_is_its_customers_and_months():
    contexts = {c["context_id"]: c for c in load("contexts.json")}
    states = {s["product_state_id"]: s for s in load("product_states.json")}
    wrong = []
    for imp in load("impressions.json"):
        ctx = contexts.get(imp["context"])
        if ctx is None or states[imp["product_state"]]["month"] != ctx["month"]:
            wrong.append(imp["impression_id"])
    assert not wrong, wrong[:5]


def test_kit_status_reads_the_kit_from_the_basket_and_what_is_owned():
    cage = {"pet_type": "small_animal", "name": "Trixie Cage", "brand": "Trixie"}
    bottle = {"pet_type": "small_animal", "name": "PetNord Water Bottle 500ml", "brand": "PetNord"}
    hideout = {"pet_type": "small_animal", "name": "Trixie Hideout", "brand": "Trixie"}
    wheel = {"pet_type": "small_animal", "name": "Trixie Exercise Wheel", "brand": "Trixie"}

    # A cage in the basket: the bottle is next; the cage itself is had.
    assert kit_status(bottle, {"small_animal_cage"}, set()) == "next"
    assert kit_status(cage, {"small_animal_cage"}, set()) == "owned"
    # Owning cage and bottle: the hideout is next, the wheel another add-on.
    owned = {"small_animal_cage", "small_animal_water_bottle"}
    assert (kit_status(hideout, set(), owned), kit_status(wheel, set(), owned)) == ("next", "other")
    # No kit started: no effect.
    assert kit_status(hideout, set(), set()) is None
