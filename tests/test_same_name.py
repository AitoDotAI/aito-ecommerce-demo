"""One card per product name (src/same_name.py).

The generated catalogue gives some SKUs the same name and details:
"Trixie Hideout" is SKU-PT-0563 and SKU-PT-0564. A list shows the name
once, as the SKU Aito ranked highest, with its own score.
"""

from dataclasses import dataclass, field

from src.same_name import one_per_name


@dataclass(frozen=True)
class Card:
    sku: str
    name: str
    p: float
    levered: bool = False
    same_name_skus: list[str] = field(default_factory=list)


def test_a_name_shows_once_as_its_highest_ranked_sku_with_that_skus_own_score():
    ranked = [Card("0544", "Veggie Crunch 100g", 0.44), Card("0554", "Fruit Drops 200g", 0.43),
              Card("0542", "Veggie Crunch 100g", 0.37)]

    cards = one_per_name(ranked)

    assert [(c.sku, c.p) for c in cards] == [("0544", 0.44), ("0554", 0.43)]   # 0.44, not 0.44 + 0.37
    assert cards[0].same_name_skus == ["0542"]
    assert cards[1].same_name_skus == []


def test_three_skus_of_one_name_make_one_card_that_lists_the_other_two():
    ranked = [Card("0553", "Fruit Drops 100g", 0.37), Card("0552", "Fruit Drops 100g", 0.32),
              Card("0550", "Fruit Drops 100g", 0.29)]

    [card] = one_per_name(ranked)

    assert card.sku == "0553" and card.same_name_skus == ["0552", "0550"]


def test_the_sku_a_lever_changed_wins_its_name_and_keeps_its_own_place():
    # In the sandbox the owner put SKU-PT-0563 on offer; its twin ranks above it.
    ranked = [Card("0564", "Trixie Hideout", 0.30), Card("0100", "Exercise Wheel", 0.28),
              Card("0563", "Trixie Hideout", 0.27, levered=True)]

    cards = one_per_name(ranked, wins=lambda c: c.levered)

    assert [c.sku for c in cards] == ["0100", "0563"]
    assert cards[1].same_name_skus == ["0564"]


def test_a_list_without_shared_names_is_unchanged():
    ranked = [Card("A", "Alpha", 0.5), Card("B", "Beta", 0.4)]

    assert one_per_name(ranked) == ranked
