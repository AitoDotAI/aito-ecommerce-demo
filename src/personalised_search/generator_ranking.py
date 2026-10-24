"""The ceiling estimate: the generator's own ranking (ADR 0037 §3).

The generator draws a search session's words from a product the shopper is
drawn to, then shows products the words could have come from, weighted by
how much this shopper wants each (`gen_impressions`). This module ranks
those products by that same weight, computed by the generator's own
functions from the shopper's hidden traits in the answer key, which Aito
never sees.

It is an estimate of the ceiling, not a strict upper bound: what was
bought was drawn from what was shown, through the purchase funnel, not
from this weight alone.
"""

from __future__ import annotations

import json
from functools import cache
from types import SimpleNamespace

from data import generate_fixtures as generator
from data import shoppers
from src.personalised_search.sessions import DATA, Session, load, load_products


@cache
def _shoppers() -> dict[str, SimpleNamespace]:
    """The answer key's rows, shaped as the generator's `Customer` for its scoring functions."""
    rows = json.loads((DATA / "answer_key" / "customer_traits.json").read_text(encoding="utf-8"))
    for row in rows:
        if "favorite_brands" not in row:
            raise KeyError(f"The answer key lacks favorite_brands for {row['customer_id']}: "
                           "run `./do generate-fixtures`")
    return {r["customer_id"]: SimpleNamespace(
        customer_id=r["customer_id"], segment=r["segment"], pet_size=r.get("pet_size"),
        diet_rule=r.get("diet_rule"), lifestyle=r["lifestyle"], health_focus=r["health_focus"],
        treat_affinity=r["treat_affinity"], brand_loyalty=r["brand_loyalty"],
        favorite_brands=tuple(r["favorite_brands"])) for r in rows}


@cache
def _catalogue() -> list[SimpleNamespace]:
    # products.json leaves out null fields, as Aito wants them; the generator reads them as None.
    return [SimpleNamespace(**{"dietary": None, "weight_kg": None, **p}) for p in load_products().values()]


@cache
def _phrases() -> dict[str, list[SimpleNamespace]]:
    return shoppers.query_phrases(_catalogue())


@cache
def _on_sale() -> frozenset[tuple[str, str]]:
    return frozenset((s["product_sku"], s["month"]) for s in load("product_states"))


def generator_weight(product: SimpleNamespace, customer: SimpleNamespace) -> float:
    """The weight `gen_impressions` gives this product for this shopper (its affinity draw)."""
    pet_type_weights = generator._segment_pet_type_weights(customer.segment, customer.pet_size)
    cat_bias = generator._category_bias_for_customer(
        generator._category_bias(customer.segment, customer.pet_size), customer)
    pt = pet_type_weights.get(product.pet_type, 0.003)
    cb = cat_bias.get(product.category, 0.05) if cat_bias else 0.1
    return max(pt * (0.5 + 5 * cb) * generator._customer_product_score(product, customer)
               * shoppers.browse_weight(product.name, product.pet_type, product.category, customer.diet_rule), 1e-4)


def generator_ranking(session: Session) -> list[str]:
    """The products the session's words could have come from, on sale that month, by the weight."""
    if session.query not in _phrases():
        raise KeyError(f"{session.session_id}: “{session.query}” is not one of the generator's phrases")
    customer = _shoppers()[session.customer]
    pool = [p for p in _phrases()[session.query] if (p.sku, session.month) in _on_sale()]
    return [p.sku for p in sorted(pool, key=lambda p: (-generator_weight(p, customer), p.sku))]
