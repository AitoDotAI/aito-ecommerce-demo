"""Relevance judgments for the search evaluation — made WITHOUT any search system.

Every query in `data/search_eval/queries.json` carries a spec over the
product's structured attributes (pet type, category, dietary, brand, a
name token). Each product in the catalogue is graded against it:

  2  fully relevant — every constraint holds
  1  partially relevant — the pet/category core holds, the refinement
     (e.g. `senior`) does not. Only when the query HAS such a core: a
     brand-only query like "royal canin" has no partial credit, or every
     product in the shop would be half-relevant.
  0  not relevant

Two properties matter more than the rule details:

* The labels are EXHAUSTIVE — all 658 products are graded, not only the
  ones some system happened to retrieve. Pooled judgments favour whichever
  system built the pool; exhaustive ones also make recall measurable.
* The labels come from attributes, not from text any arm searches. That is
  why a vector arm must embed the same text the lexical arm searches (the
  product name): embedding the dietary/category fields these rules read
  would let it read the answer key.
"""

from __future__ import annotations

import json
from pathlib import Path

QUERIES_PATH = Path(__file__).resolve().parents[2] / "data" / "search_eval" / "queries.json"
PRODUCTS_PATH = Path(__file__).resolve().parents[2] / "data" / "products.json"


def load_queries() -> list[dict]:
    return json.loads(QUERIES_PATH.read_text())["queries"]


def load_products() -> list[dict]:
    return json.loads(PRODUCTS_PATH.read_text())


def _refinement_holds(refine: dict, product: dict) -> bool:
    name = product["name"].lower()
    if "dietary" in refine:
        return product.get("dietary") == refine["dietary"]
    if "brand" in refine:
        return product["brand"] == refine["brand"]
    if "token_any" in refine:
        return any(tok.lower() in name for tok in refine["token_any"])
    raise ValueError(f"unknown refinement {sorted(refine)}")


def grade(query: dict, product: dict) -> int:
    """0/1/2 relevance of one product for one query spec."""
    pet, categories, refine = query.get("pet"), query.get("categories"), query.get("refine")
    has_core = pet is not None or categories is not None
    core = (pet is None or product["pet_type"] == pet) and (
        categories is None or product["category"] in categories
    )
    if not core:
        return 0
    if refine is None:
        return 2 if has_core else 0
    if _refinement_holds(refine, product):
        return 2
    return 1 if has_core else 0


def judge(query: dict, products: list[dict]) -> dict[str, int]:
    """{sku: grade} for every product with a non-zero grade."""
    return {p["sku"]: g for p in products if (g := grade(query, p)) > 0}
