"""Retention's win-back offer: candidates for the customer's pets, the
calibrated chance they respond, and the best expected return.

A fake client answers the batched `_recommend`s and `_predict`s, the
product read and each `_estimate`, and records what it was asked.
"""

from __future__ import annotations

from src.winback_offer import EMAIL_COST_EUR, offers_for

PRODUCTS = {
    "FOOD": {"sku": "FOOD", "name": "Guinea Pig Food", "pet_type": "small_animal", "category": "dry-food",
             "price_eur": 20.0},
    "HAY": {"sku": "HAY", "name": "Meadow Hay", "pet_type": "small_animal", "category": "hay", "price_eur": 5.0},
}


class WinbackAito:
    def __init__(self, candidates=("FOOD", "HAY")):
        self.candidates = list(candidates)
        self.batches: list[list[dict]] = []
        self.estimates: list[dict] = []

    def search(self, table, where=None, limit=10, offset=0, **_):
        if table == "winback_campaigns":     # the customers' past sends: their staple
            return {"hits": [{"customer_id": "C1", "customer_staple_category": "small_animal/dry-food"}],
                    "total": 1}
        return {"hits": [PRODUCTS[s] for s in where["sku"]["$or"]], "total": len(where["sku"]["$or"])}

    def batch(self, queries):
        self.batches.append(queries)
        if "recommend" in queries[0]:
            # A batch item's hit is only `$p` and `$value`; the $p is never shown.
            return [{"hits": [{"$p": 0.99, "$value": s} for s in self.candidates]} for _ in queries]
        rate = {"FOOD": 0.2, "HAY": 0.5}
        return [{"hits": [{"feature": True, "$p": rate[q["where"]["product_sku"]]},
                          {"feature": False, "$p": 1 - rate[q["where"]["product_sku"]]}]} for q in queries]

    def estimate(self, table, where, estimate_field, model=None, with_why=True):
        self.estimates.append(where)
        return {"estimate": {"FOOD": 90.0, "HAY": 12.0}[where["product_sku"]]}


def test_candidates_are_only_products_for_the_customers_own_pets():
    fake = WinbackAito()

    offers_for(fake, {"C1": ["small_animal"]})

    [recommend] = fake.batches[0]
    # A `product_sku.*` key filters the candidates; the rest is context.
    assert recommend["where"]["product_sku.pet_type"] == {"$or": ["small_animal"]}
    assert recommend["where"]["customer_staple_category"] == "small_animal/dry-food"
    assert recommend["goal"] == {"responded": True}


def test_the_offer_is_the_best_expected_return_not_the_likeliest_response():
    offers = offers_for(WinbackAito(), {"C1": ["small_animal"]})

    offer = offers["C1"]
    # Hay responds more often (50 % vs 20 %) but food orders are bigger: 0.2 × 90 > 0.5 × 12.
    assert offer.sku == "FOOD"
    assert offer.response_p == 0.2
    assert offer.expected_return_eur == round(0.2 * 90.0 - EMAIL_COST_EUR, 2)


def test_the_order_value_is_estimated_given_a_response():
    fake = WinbackAito()

    offers_for(fake, {"C1": ["small_animal"]})

    assert all(w["responded"] is True for w in fake.estimates)


def test_no_past_email_for_the_customers_pets_means_no_offer_not_a_wrong_one():
    offers = offers_for(WinbackAito(candidates=()), {"C2": ["aquarium"]})

    assert offers == {"C2": None}
