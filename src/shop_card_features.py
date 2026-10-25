"""Which features lie behind a Shop card's pull: the patterns of a product, one lift each.

The card's `$why` (`shop_why.py`) holds the product's features as one lift ("products with
this one's features", `hitLinkPropositionLift`) and gives no parts. This asks Aito for the
parts: `_predict purchased` on `impressions` with the product's features as conditions, in place
of its SKU, and the shopper's situation as context. Each feature's lift comes back in `$why`.

It is a second query, not the first one opened up: its probability is lower than the card's
(the card knows the product itself) and its lifts don't multiply to the card's percentage.
Only the product's own features are listed; the situation's lifts are in the card's chain.

Aito also estimates some features as a group and gives the group one lift, which overlaps the
single lifts. Those come apart from the single ones (`joint`), as `shop_reasons` does for a
card's reasons, so the single lifts are not read as a product that includes them.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass

from src.aito_client import AitoClient, AitoError
from src.shop_ranking import shop_scope
from src.why_processor import _flatten_proposition

PRODUCT_TEXT = {"name": "Name", "tags": "Tags"}                 # matched word by word
PRODUCT_VALUES = {"brand": "Brand", "category": "Category", "pet_type": "Pet"}
STATE_VALUES = {"discount_band": "Offer", "rating_band": "Stars", "age": "Age", "label": "Label",
                "stock": "Stock", "review_count_band": "Reviews", "price_change": "Price change",
                "rival_launched": "Rival launched", "on_offer": "On offer"}


@dataclass(frozen=True)
class Feature:
    label: str                       # "Brand is Trixie", "Name has the word Hideout"
    marked_text: str | None = None   # a text feature's field value, the matched word marked


@dataclass(frozen=True)
class FeaturePattern:
    """One lift of Aito's. Several features share one when Aito estimates them as a group: it
    gives the group a single lift, so they are listed together, never one lift each."""
    lift: float                      # how much it multiplies the odds of a purchase
    features: list[Feature]


@dataclass(frozen=True)
class CardFeatures:
    sku: str
    p: float                         # this query's probability, not the card's
    base_p: float
    patterns: list[FeaturePattern]   # one feature, one lift; biggest effect first
    joint: list[FeaturePattern]      # several features, Aito's lift for them together; same order

    def to_dict(self) -> dict:
        return asdict(self)


def get_card_features(client: AitoClient, shopper_key: str, month: str, cart_skus: list[str],
                      sku: str) -> CardFeatures:
    scope = shop_scope(client, shopper_key, month, cart_skus)
    product = _one(client, "products", {"sku": sku})
    state = _one(client, "product_states", {"product_sku": sku, "month": month})
    where = {**scope.context, "just_bought": False}
    for column, text in PRODUCT_TEXT.items():
        where[f"product_sku.{column}"] = {"$match": product[column]}
    where.update({f"product_sku.{c}": product[c] for c in PRODUCT_VALUES})
    where.update({f"product_state.{c}": state[c] for c in STATE_VALUES})
    answer = client.predict("impressions", where, "purchased")
    hit = next((h for h in answer["hits"] if h.get("feature", h.get("$value")) is True), None)
    if hit is None:
        raise AitoError(f"_predict purchased for {sku} had no `true` hit: {json.dumps(answer)[:300]}")
    return features_from(hit, sku, product)


def features_from(hit: dict, sku: str, product: dict) -> CardFeatures:
    """The `true` hit's per-feature lifts, as patterns, biggest effect first."""
    base_p = next(f["value"] for f in hit["$why"]["factors"] if f["type"] == "baseP")
    found = []
    for factor in hit["$why"]["factors"]:
        if factor["type"] != "relatedPropositionLift":
            continue
        propositions = _flatten_proposition(factor["proposition"])
        fields = {p["field"] for p in propositions}
        if not all(f.startswith(("product_sku.", "product_state.")) for f in fields):
            continue          # the situation: shown in the card's chain
        found.append(FeaturePattern(float(factor["value"]), _features(propositions, product)))
    found.sort(key=lambda p: -abs(math.log(p.lift)))
    return CardFeatures(
        sku=sku, p=round(float(hit["$p"]), 4), base_p=round(float(base_p), 4),
        patterns=[p for p in found if len(p.features) == 1], joint=[p for p in found if len(p.features) > 1])


def _features(propositions: list[dict], product: dict) -> list[Feature]:
    out = []
    for prop in propositions:
        kind, column = prop["field"].split(".", 1)
        value = prop["value"]
        if kind == "product_sku" and column in PRODUCT_TEXT:
            marked = " ".join(f"«{w}»" if w == value else w for w in product[column].split())
            out.append(Feature(f"{PRODUCT_TEXT[column]} has the word {value}", marked))
        elif kind == "product_sku" and column in PRODUCT_VALUES:
            out.append(Feature(f"{PRODUCT_VALUES[column]} is {value}"))
        elif kind == "product_state" and column in STATE_VALUES:
            out.append(Feature(f"{STATE_VALUES[column]}: {value}"))
        else:
            raise AitoError(f"Unexpected feature in `$why`: {prop}")
    return out


def _one(client: AitoClient, table: str, where: dict) -> dict:
    hits = client.search(table, where=where, limit=1)["hits"]
    if not hits:
        raise AitoError(f"No {table} row for {where}")
    return hits[0]
