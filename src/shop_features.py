"""The features a Shop card's "products with this one's features" term stands for.

`_recommend`'s `$why` gives that term as one lift and says nothing of its parts, and returns no
highlights for it (probed 2026-10-25, 2.11.8; asked of core in td-20261025110436725926). Until it does,
the card shows the features themselves: the tokens Aito holds for the product, with no lift per
token. Text columns (name, tags) are split on whitespace, as their analyzer does; the rest are
single values.
"""

from __future__ import annotations

from dataclasses import dataclass

TEXT = {"name": "Name", "tags": "Tags"}
PRODUCT = {"brand": "Brand", "category": "Category", "pet_type": "Pet"}
STATE = {"discount_band": "Offer", "rating_band": "Stars", "age": "Age", "label": "Label",
         "stock": "Stock", "review_count_band": "Reviews", "price_change": "Price change",
         "rival_launched": "Rival launched", "on_offer": "On offer"}


@dataclass(frozen=True)
class ProductFeature:
    field: str            # "Name", "Brand", "Offer"
    tokens: list[str]     # a text column's words, or the one value


def product_features(product: dict, state: dict | None) -> list[ProductFeature]:
    """The product's text, product and state columns as tokens; a column with no value is left out.

    `state` is None when the product has no state row for the month (the sandbox's 2026-05 holds
    only the rows its levers wrote): then only the product's own columns are listed."""
    features = [ProductFeature(label, str(product[column]).split()) for column, label in TEXT.items() if product.get(column)]
    features += [ProductFeature(label, [str(product[column])]) for column, label in PRODUCT.items()]
    if state is not None:
        features += [ProductFeature(label, [str(state[column]).lower() if isinstance(state[column], bool) else str(state[column])])
                     for column, label in STATE.items()]
    return features
