"""Reading a product's reasons from `_recommend`'s `$why` (src/shop_reasons.py).

The `$why` below is the shape Aito 2.11.4 returned for Sofia, with a cage
in her cart, on a fruit treat (2026-10-17), trimmed to the factors used.
"""

import pytest

from src.aito_client import AitoError
from src.shop_reasons import Reason, reasons_for

SKU = "SKU-PT-0553"


def why(*nested, sku=SKU):
    return {"type": "product", "factors": [
        {"type": "baseP", "proposition": {"purchased": True}, "value": 0.105},
        {"type": "hitLinkPropositionLift", "proposition": {"product_sku": {"$has": sku}}, "value": 1.05},
        {"type": "hitPropositionLift", "proposition": {"product_sku": {"$has": sku}}, "value": 7.97,
         "factors": [{"type": "relatedPropositionLift", "proposition": p, "value": v} for p, v in nested]},
        # Lifts of *other* products not being the hit: not this product's reasons.
        {"type": "hitPropositionLift", "proposition": {"$not": {"product_sku": {"$has": "SKU-PT-0545"}}},
         "value": 0.98, "factors": [{"type": "relatedPropositionLift",
                                     "proposition": {"customer_treat_affinity": "high"}, "value": 9.0}]},
    ]}


def test_the_largest_lifts_nested_under_the_product_itself_are_its_reasons():
    reasons = reasons_for(why(({"customer_treat_affinity": "high"}, 1.49),
                              ({"month": "2026-04"}, 1.32),
                              ({"customer_lifestyle": "mid"}, 1.04)), SKU)

    # ×1.04 is below MIN_REASON_LIFT; the other product's ×9.0 isn't this one's.
    assert reasons == [Reason("Treat affinity: high", 1.49), Reason("Sells in April", 1.32)]


def test_the_carts_factors_multiply_into_one_reason():
    reasons = reasons_for(why(({"$and": [{"basket_skus": {"$match": "SKU-PT-0555"}}]}, 1.25),
                              ({"$group": [{"$and": [{"basket_categories": {"$match": "small_animal_cage"}}]}]}, 2.38)),
                          SKU)

    assert reasons == [Reason("Goes with your cart", 2.97)]   # 1.25 × 2.38


def test_at_most_three_reasons_are_kept_and_just_bought_is_never_one():
    reasons = reasons_for(why(({"just_bought": False}, 1.9),
                              ({"customer_segment": "small_animal_owner"}, 1.2),
                              ({"customer_health_focus": "low"}, 2.0),
                              ({"customer_brand_loyalty": "loyal"}, 1.6),
                              ({"customer_treat_affinity": "high"}, 1.5)), SKU)

    assert [r.label for r in reasons] == ["Health focus: low", "Brand loyalty: loyal", "Treat affinity: high"]


def test_a_product_aito_knows_only_by_its_features_has_no_reasons():
    # Too few impressions of its own: only the link prior, no lift to break down.
    thin = {"type": "product", "factors": [
        {"type": "baseP", "proposition": {"purchased": True}, "value": 0.105},
        {"type": "hitLinkPropositionLift", "proposition": {"product_sku": {"$has": SKU}}, "value": 1.6}]}

    assert reasons_for(thin, SKU) == []


def test_an_unknown_proposition_raises_rather_than_being_dropped():
    with pytest.raises(AitoError, match="Unexpected"):
        reasons_for(why(({"customer_pet_size": "small"}, 1.5)), SKU)
