"""The Shop's suggestions (src/shop_suggestions.py), against a fake Aito."""

from src.shop_suggestions import get_suggestions

PRODUCTS = {
    "SKU-CAGE": {"sku": "SKU-CAGE", "name": "Trixie Cage", "brand": "Trixie", "pet_type": "small_animal"},
    "SKU-FOOD": {"sku": "SKU-FOOD", "name": "PetNord Hamster Mix Food 1kg", "brand": "PetNord", "pet_type": "small_animal"},
    "SKU-HIDE": {"sku": "SKU-HIDE", "name": "Trixie Hideout", "brand": "Trixie", "pet_type": "small_animal"},
}


class FakeAito:
    def __init__(self, orders):
        self.orders = orders
        self.predicts: list[dict] = []

    def search(self, table, *, where, limit=10, **_):
        if table == "orders":
            return {"hits": self.orders, "total": len(self.orders)}
        return {"hits": [PRODUCTS.get(s, {"sku": s, "name": f"Name {s}", "brand": "B", "pet_type": "x"})
                         for s in where["sku"]["$or"]]}

    def predict_rows(self, population, predict_field, *, where=None, limit=10):
        self.predicts.append({"from": population, "where": where, "predict": predict_field})
        if predict_field == "skus.$feature":
            return {"hits": [{"feature": "SKU-FOOD", "$p": 0.41}, {"feature": "SKU-CAGE", "$p": 0.12}]}
        return {"hits": [
            {"sku": "SKU-W", "name": "PetNord Exercise Wheel", "brand": "PetNord", "$p": 0.25},
            {"sku": "SKU-H", "name": "Trixie Hideout", "brand": "Trixie", "$p": 0.30},
        ]}


# As the generator writes them: owned_before lists what earlier orders bought.
SOFIA_ORDERS = [
    {"order_id": "O1", "month": "2026-01", "skus": "SKU-CAGE SKU-FOOD", "owned_before": None},
    {"order_id": "O2", "month": "2026-02", "skus": "SKU-FOOD SKU-HIDE", "owned_before": "small_animal_cage"},
    {"order_id": "O3", "month": "2026-06", "skus": "SKU-FOOD", "owned_before": "small_animal_cage small_animal_hideout"},
]


def test_the_usual_basket_is_one_probability_per_product_from_the_shoppers_own_orders():
    fake = FakeAito(SOFIA_ORDERS)

    result = get_suggestions(fake, "sofia", "2026-04")

    usual_query = fake.predicts[0]
    # Her orders before April 2026, not the June one.
    assert usual_query["from"] == {"from": "orders", "where": {"order_id": {"$or": ["O1", "O2"]}}}
    assert usual_query["predict"] == "skus.$feature"
    # The cage is in her history but bought once: not part of the usual basket.
    assert [(s.sku, s.p) for s in result.usual] == [("SKU-FOOD", 0.41)]


def test_whats_next_conditions_on_everything_owned_and_skips_what_is_owned():
    fake = FakeAito(SOFIA_ORDERS)

    result = get_suggestions(fake, "sofia", "2026-04")

    next_query = fake.predicts[1]
    assert next_query["where"]["order_id.owned_before"] == {"$and": [
        {"$match": "small_animal_cage"}, {"$match": "small_animal_hideout"}]}
    assert result.owned == {"small_animal": ["cage", "hideout"]}
    # The hideout scores higher, but she owns one; the wheel is next.
    assert [s.sku for s in result.next_for_pet] == ["SKU-W"]


def test_a_shopper_without_orders_gets_no_suggestions_and_is_told_why():
    result = get_suggestions(FakeAito([]), "sofia", "2026-04")

    assert result.no_history and result.usual == [] and result.next_for_pet == []


def test_whats_next_says_nothing_when_only_noise_is_left():
    fake = FakeAito(SOFIA_ORDERS)
    real = fake.predict_rows
    fake.predict_rows = lambda population, field, where=None, limit=10: (
        real(population, field, where=where, limit=limit) if field == "skus.$feature"
        else {"hits": [{"sku": "SKU-T", "name": "Trixie Tunnel", "brand": "Trixie", "$p": 0.005}]})

    assert get_suggestions(fake, "sofia", "2026-04").next_for_pet == []


def test_a_month_before_any_order_has_no_history_yet():
    assert get_suggestions(FakeAito(SOFIA_ORDERS), "sofia", "2025-12").no_history
