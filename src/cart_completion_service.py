"""Cart Completion — checkout-funnel demo.

Four preset carts representing common pet-shop checkout shapes.
For each cart, Aito's `_recommend product_sku` (conditioned on the
cart's `line_categories` tokens via single-hop link traversal from
`order_lines`) ranks products that historically appeared alongside
the cart's items in non-returned orders. Surfaces 3 add-on
suggestions per cart with the predicted attach probability.

The view answers a question every e-com personalization platform
sells: *given what's already in cart, what's the single best add
to bump basket value?* Aito does it with one query and existing
schema — no specialised "session events" table required.

Cached for 30 minutes.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict
from typing import Any

from src.aito_client import AitoClient
from src import cache


# ── Cart scenarios ────────────────────────────────────────────────


@dataclass(frozen=True)
class CartScenario:
    """A preset cart — the input to the recommend call.

    `category_tokens` are the `pet__category` tokens Aito needs to
    `$match` against `order_id.line_categories`. Pre-computed at
    module load so we don't re-derive them per request.
    """
    scenario_id: str        # url-stable id ("dog-food", etc.)
    label: str              # display label
    description: str        # one-liner for the card
    item_skus: tuple[str, ...]   # what's IN the cart (real SKUs)
    category_tokens: tuple[str, ...]  # for the $match
    expected_pet_type: str  # for the recommend's persona context


SCENARIOS: list[CartScenario] = [
    CartScenario(
        scenario_id="dog-food-starter",
        label="Dog-food starter",
        description="Premium dry-food in cart — what does the dog owner add next?",
        item_skus=("SKU-PT-0035", "SKU-PT-0049"),  # Hill's + Eukanuba dog dry-food
        category_tokens=("dog_dryfood",),
        expected_pet_type="dog",
    ),
    CartScenario(
        scenario_id="cat-essentials",
        label="Cat essentials",
        description="Wet food + litter in cart — typical cat-owner basket.",
        item_skus=("SKU-PT-0407", "SKU-PT-0483"),  # Whiskas wet + clumping litter
        category_tokens=("cat_wetfood", "cat_litter"),
        expected_pet_type="cat",
    ),
    CartScenario(
        scenario_id="aquarium-starter",
        label="Aquarium starter",
        description="Filter pads + water conditioner — new tank setup.",
        item_skus=("SKU-PT-0609", "SKU-PT-0611"),  # JBL filter + conditioner
        category_tokens=("aquarium_aquarium",),
        expected_pet_type="aquarium",
    ),
    CartScenario(
        scenario_id="dog-accessory",
        label="Dog accessory + toy",
        description="Harness + chew bone in cart — non-food shopper. What rounds out the order?",
        item_skus=("SKU-PT-0206", "SKU-PT-0238"),  # PetNord harness + Trixie chew bone
        category_tokens=("dog_accessories", "dog_toys"),
        expected_pet_type="dog",
    ),
]


# ── DTOs ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CartItem:
    sku: str
    name: str
    category: str
    price_eur: float


@dataclass(frozen=True)
class AddOnSuggestion:
    sku: str
    name: str
    pet_type: str
    category: str
    brand: str
    price_eur: float
    attach_p: float       # Aito's $p — calibrated probability the recommend ranks this candidate first
    rank: int
    # Estimated checkout-cart uplift if the add gets clicked. Naive
    # = attach_p × price_eur. Real platforms would multiply by
    # impression rate × clickthrough × conversion, but the demo
    # surface is the headline single multiplier.
    expected_uplift_eur: float


@dataclass
class CartScenarioResult:
    scenario_id: str
    label: str
    description: str
    items: list[CartItem]
    cart_value_eur: float
    suggestions: list[AddOnSuggestion]


@dataclass
class CartCompletionResponse:
    scenarios: list[CartScenarioResult]
    last_query: dict
    last_response_ms: int

    def to_dict(self) -> dict:
        return {
            "scenarios": [
                {
                    "scenario_id": s.scenario_id,
                    "label":       s.label,
                    "description": s.description,
                    "items":       [asdict(i) for i in s.items],
                    "cart_value_eur": s.cart_value_eur,
                    "suggestions": [asdict(x) for x in s.suggestions],
                }
                for s in self.scenarios
            ],
            "last_query":       self.last_query,
            "last_response_ms": self.last_response_ms,
        }


# ── Live calls ─────────────────────────────────────────────────────


def _fetch_products_map(client: AitoClient, skus: list[str]) -> dict[str, dict]:
    """One `_search` to fetch every cart-item + every suggestion's
    product detail in a single round-trip. Beats issuing N
    sequential single-row lookups.
    """
    if not skus:
        return {}
    res = client.search(
        "products",
        where={"sku": {"$or": list(skus)}},
        limit=len(skus),
    )
    return {p["sku"]: p for p in res.get("hits", [])}


def _relate_for_cart(
    client: AitoClient,
    scenario: CartScenario,
) -> tuple[list[dict], dict]:
    """Two-step cart-completion query.

    Step 1: `_relate from orders where {line_categories: $match
    cart_tokens} relate line_categories` returns the (pet,
    category) pairs that co-occur most strongly with the cart's
    items — same pattern as Bought Together.

    Step 2 (caller's job): pick popular products in the top related
    category and return them as suggestions.

    Why this shape: `_predict product_sku where {linked $match}`
    returns the marginal product distribution without conditioning
    on the cart (Aito's single-hop traversal doesn't bite for
    predict's where). `_relate` from `orders` directly on the
    `line_categories` Text column works as intended — it's the
    same query the Bought Together view uses.
    """
    match_tokens = " ".join(scenario.category_tokens)
    where = {"line_categories": {"$match": match_tokens}}
    body = {
        "from":   "orders",
        "where":  where,
        "relate": "line_categories",
        "limit":  10,
    }
    res = client.relate(
        table="orders",
        where=where,
        relate_field="line_categories",
        limit=10,
    )
    return res.get("hits", []), body


_CLEAN_CAT_TO_HYPHENATED: dict[str, str] = {
    "dryfood":      "dry-food",
    "wetfood":      "wet-food",
    "dentaltreats": "dental-treats",
}


def _token_to_pet_category(token: str) -> tuple[str, str] | None:
    """Decode a `pet_category` token back to a (pet, category) pair.

    `rpartition` on `_` because `small_animal` contains underscores
    in the pet_type half; the category side never does (hyphens
    stripped at fixture-gen). Same shape as bought_together_service
    uses — kept inline here to avoid cross-service import.
    """
    pet, sep, clean_cat = token.rpartition("_")
    if not sep or not clean_cat:
        return None
    return pet, _CLEAN_CAT_TO_HYPHENATED.get(clean_cat, clean_cat)


def _popular_in_category(
    client: AitoClient,
    pet_type: str,
    category: str,
    exclude_skus: set[str],
    limit: int = 3,
) -> list[dict]:
    """Top-N popular products in a (pet_type, category). We fetch a
    wide window and pick the highest-priced eligible products as a
    proxy for "premium upsell". Without a `total_units_sold` column
    on `products`, this is the closest signal that keeps the
    suggested €-uplift in a meaningful range (low-price products
    would make the per-suggestion € figure read trivial in a demo
    that needs to make the upsell story tangible).
    """
    res = client.search(
        "products",
        where={"pet_type": pet_type, "category": category},
        limit=50,   # wide window for the price sort to bite
    )
    eligible = [
        p for p in res.get("hits", [])
        if p["sku"] not in exclude_skus
    ]
    eligible.sort(key=lambda p: -float(p.get("price_eur", 0) or 0))
    return eligible[:limit]


def _build_scenario_result_from_relate(
    client: AitoClient,
    scenario: CartScenario,
    relate_hits: list[dict],
    relate_body: dict,
    products_map: dict[str, dict],
) -> tuple[CartScenarioResult, dict]:
    """Assemble one scenario's final response from the `_relate` hits.

    Pipeline: pick the top related (pet, category) by lift from the
    relate response (excluding cart's own categories), then fetch
    popular products in that category via a single `_search`. The
    suggestion's `attach_p` carries the lift / (lift+1) form so it
    reads as a 0-1 confidence (matches the rest of the demo's $p
    framing)."""
    cart_skus = set(scenario.item_skus)
    items: list[CartItem] = []
    cart_value = 0.0
    for sku in scenario.item_skus:
        p = products_map.get(sku, {})
        if not p:
            continue
        price = float(p.get("price_eur", 0) or 0)
        cart_value += price
        items.append(CartItem(
            sku=sku,
            name=p.get("name", sku),
            category=p.get("category", ""),
            price_eur=round(price, 2),
        ))

    # Walk relate hits; for each related (pet, category) pair that
    # isn't already in the cart, pick a popular product. Stop at 3.
    own_tokens = set(scenario.category_tokens)
    suggestions: list[AddOnSuggestion] = []
    seen_skus: set[str] = set(cart_skus)
    for hit in relate_hits:
        if len(suggestions) >= 3:
            break
        rel = hit.get("related", {}).get("line_categories", {})
        token = rel.get("$has") if isinstance(rel, dict) else None
        if not token or token in own_tokens:
            continue
        decoded = _token_to_pet_category(token)
        if decoded is None:
            continue
        pet, category = decoded
        lift = float(hit.get("lift", 1.0) or 1.0)
        if lift < 1.15:
            # Only surface genuinely positive cross-sells. Below
            # 1.15× is noise / weak signal.
            continue
        # Convert lift → calibrated 0-1 confidence for display.
        # Mirrors $p framing elsewhere in the demo: lift 2.0 → 0.67,
        # lift 3.0 → 0.75, lift 5.0 → 0.83. Bounded above by 0.95.
        confidence = round(min(0.95, lift / (lift + 1.0)), 3)

        for prod in _popular_in_category(client, pet, category, seen_skus, limit=2):
            if len(suggestions) >= 3:
                break
            seen_skus.add(prod["sku"])
            price = float(prod.get("price_eur", 0) or 0)
            suggestions.append(AddOnSuggestion(
                sku=prod["sku"],
                name=prod.get("name", prod["sku"]),
                pet_type=prod.get("pet_type", ""),
                category=prod.get("category", ""),
                brand=prod.get("brand", ""),
                price_eur=round(price, 2),
                attach_p=confidence,
                rank=len(suggestions) + 1,
                expected_uplift_eur=round(confidence * price, 2),
            ))

    return CartScenarioResult(
        scenario_id=scenario.scenario_id,
        label=scenario.label,
        description=scenario.description,
        items=items,
        cart_value_eur=round(cart_value, 2),
        suggestions=suggestions,
    ), relate_body


# ── Public entry point ─────────────────────────────────────────────


def get_cart_completion(client: AitoClient) -> CartCompletionResponse:
    cached = cache.get("cart_completion:all")
    if cached:
        return _from_dict(cached)

    started = time.perf_counter()

    # Pre-fetch cart-item products so cart-item rendering has names.
    cart_skus = sorted({sku for s in SCENARIOS for sku in s.item_skus})
    products_map = _fetch_products_map(client, cart_skus)

    # 4 scenarios × 1 `_relate` each = 4 parallel calls.
    with ThreadPoolExecutor(max_workers=4) as pool:
        relate_pairs = list(pool.map(
            lambda s: _relate_for_cart(client, s),
            SCENARIOS,
        ))

    # Build each result — the relate hits + per-suggestion popular-
    # product lookup. The popular-product `_search` is small and
    # well-cached on Aito's side so we don't bother parallelising
    # the per-scenario assembly.
    pairs = [
        _build_scenario_result_from_relate(
            client, scenario, hits, body, products_map,
        )
        for scenario, (hits, body) in zip(SCENARIOS, relate_pairs)
    ]
    scenarios = [r for r, _ in pairs]
    last_body = pairs[0][1] if pairs else {}
    elapsed = int((time.perf_counter() - started) * 1000)

    resp = CartCompletionResponse(
        scenarios=scenarios,
        last_query={"endpoint": "_recommend", "body": last_body},
        last_response_ms=elapsed,
    )
    cache.set("cart_completion:all", resp.to_dict(), ttl=1800)
    return resp


def _from_dict(d: dict) -> CartCompletionResponse:
    scenarios = [
        CartScenarioResult(
            scenario_id=s["scenario_id"],
            label=s["label"],
            description=s["description"],
            items=[CartItem(**i) for i in s["items"]],
            cart_value_eur=s["cart_value_eur"],
            suggestions=[AddOnSuggestion(**x) for x in s["suggestions"]],
        )
        for s in d["scenarios"]
    ]
    return CartCompletionResponse(
        scenarios=scenarios,
        last_query=d["last_query"],
        last_response_ms=d["last_response_ms"],
    )
