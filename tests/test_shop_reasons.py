"""Reading a product's reasons from `_recommend`'s `$why` (src/shop_reasons.py).

The `$why` below is the shape Aito 2.11.4 returned for a guinea-pig owner
with a cage in the cart, on a fruit treat (2026-10-17), trimmed to the
factors used, with the `where` fields renamed to ADR 0033's context form.
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
                                     "proposition": {"context.month": "2026-04"}, "value": 9.0}]},
    ]}


def test_the_largest_lifts_nested_under_the_product_itself_are_its_reasons():
    reasons = reasons_for(why(({"context.owned": {"$and": [{"$match": "small_animal_cage"}]}}, 1.49),
                              ({"context.month": "2026-04"}, 1.32),
                              ({"context.customer": "CUST-01177"}, 1.04)), SKU)

    # ×1.04 is below MIN_REASON_LIFT; the other product's ×9.0 isn't this one's.
    assert reasons == [Reason("Fits the kit you have", 1.49), Reason("Sells in April", 1.32)]


def test_the_carts_factors_multiply_into_one_reason():
    reasons = reasons_for(why(({"$and": [{"context.basket_categories": {"$match": "small_animal_cage"}}]}, 1.25),
                              ({"$and": [{"context.basket_categories": {"$match": "small_animal_accessories"}}]}, 2.38)),
                          SKU)

    assert reasons == [Reason("Goes with your cart", 2.97)]   # 1.25 × 2.38


def test_a_joint_group_is_never_shown_as_a_reason():
    # A `$group` is Aito's joint estimate of several conditions; it can rest on
    # no rows at all, so until `$why` reports support it isn't a reason.
    group = {"$group": [{"$and": [{"context.basket_categories": {"$match": "small_animal_dryfood"}}]},
                        {"$and": [{"context.owned": {"$match": "small_animal_cage"}}]}]}
    assert reasons_for(why((group, 3.4), ({"context.month": "2026-04"}, 1.3)), SKU) == [Reason("Sells in April", 1.3)]


def test_at_most_three_reasons_are_kept_and_just_bought_is_never_one():
    reasons = reasons_for(why(({"just_bought": False}, 1.9),
                              ({"context.customer.region": "oulu"}, 1.2),
                              ({"context.customer": "CUST-01177"}, 2.0),
                              ({"context.owned": {"$and": [{"$match": "small_animal_cage"}]}}, 1.6),
                              ({"context.month": "2026-04"}, 1.5)), SKU)

    assert [r.label for r in reasons] == ["Your own history", "Fits the kit you have", "Sells in April"]


def test_a_product_aito_knows_only_by_its_features_has_no_reasons():
    # Too few impressions of its own: only the link prior, no lift to break down.
    thin = {"type": "product", "factors": [
        {"type": "baseP", "proposition": {"purchased": True}, "value": 0.105},
        {"type": "hitLinkPropositionLift", "proposition": {"product_sku": {"$has": SKU}}, "value": 1.6}]}

    assert reasons_for(thin, SKU) == []


def test_an_unknown_proposition_raises_rather_than_being_dropped():
    with pytest.raises(AitoError, match="Unexpected"):
        reasons_for(why(({"customer_lifestyle": "premium"}, 1.5)), SKU)   # a hidden trait must never appear
