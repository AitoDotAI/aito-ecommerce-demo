"""Deterministic fixture generator for PetNord.

Run with `./do generate-fixtures` (or `uv run python data/generate_fixtures.py`).
Same `RNG_SEED` produces byte-identical JSON across machines.

The generator is the single source of truth for the demo's signal.
The five demo moments in `TASK.md` are *engineered into the data*
here; if a downstream view doesn't show its moment, the bug is
either here or in a query — never wallpaper it in panel copy.

Read alongside `docs/adr/0002-data-model-and-fixtures.md` — the ADR
locks the schema, vocabularies, and target signal ranges; this file
is the implementation that makes those ranges land.
"""

from __future__ import annotations

import json
import random
from collections import Counter
from dataclasses import dataclass, asdict, field
from datetime import date
from pathlib import Path
from typing import Iterable

RNG_SEED = 42
DATA_DIR = Path(__file__).resolve().parent

# ── Vocabulary (ADR 0002 §Categorical vocabularies) ─────────────────

PET_TYPES: list[str] = ["dog", "cat", "small_animal", "bird", "aquarium"]

CATEGORIES: list[str] = [
    "dry-food", "wet-food", "treats", "dental-treats",
    "litter", "accessories", "health", "grooming", "toys", "aquarium",
]

# Brand × (pet_type, category) compatibility table. Each brand only
# sells into the categories listed here. Keeps the generator from
# emitting nonsense like "Whiskas Aquarium Filter Pads", and cuts the
# raw SKU count without losing any pet_type × category coverage.
BRAND_CATEGORIES: dict[str, dict[str, list[str]]] = {
    "Royal Canin":         {"dog": ["dry-food", "wet-food"],
                            "cat": ["dry-food", "wet-food"]},
    "Hill's Science Plan": {"dog": ["dry-food", "wet-food"],
                            "cat": ["dry-food", "wet-food"]},
    "Eukanuba":            {"dog": ["dry-food", "wet-food"]},
    "Acana":               {"dog": ["dry-food"],
                            "cat": ["dry-food"]},
    "Orijen":              {"dog": ["dry-food"],
                            "cat": ["dry-food"]},
    "Whiskas":             {"cat": ["dry-food", "wet-food", "treats"]},
    "Felix":               {"cat": ["wet-food", "treats"]},
    "Sheba":               {"cat": ["wet-food"]},
    "Whimzees":            {"dog": ["dental-treats"]},
    "Kong":                {"dog": ["toys"], "cat": ["toys"]},
    "JBL":                 {"aquarium": ["aquarium", "health"]},
    "Tetra":               {"aquarium": ["aquarium"]},
    "PetNord":             {"dog": ["treats", "dental-treats", "accessories",
                                    "toys", "health", "grooming"],
                            "cat": ["treats", "litter", "accessories",
                                    "toys", "health", "grooming"],
                            "small_animal": ["dry-food", "treats", "accessories",
                                             "toys", "health"],
                            "bird": ["dry-food", "treats", "accessories", "toys"],
                            "aquarium": ["aquarium", "health"]},
    "Beaphar":             {"small_animal": ["health"],
                            "bird":         ["health"]},
    "Trixie":              {"dog": ["accessories", "toys"],
                            "cat": ["accessories", "toys"],
                            "small_animal": ["accessories", "toys"]},
}

# Which (pet_type, category) pairs are realistic. Drives product mix.
PET_CATEGORY_PAIRS: list[tuple[str, str]] = [
    ("dog", "dry-food"), ("dog", "wet-food"), ("dog", "treats"),
    ("dog", "dental-treats"), ("dog", "accessories"), ("dog", "toys"),
    ("dog", "health"), ("dog", "grooming"),
    ("cat", "dry-food"), ("cat", "wet-food"), ("cat", "treats"),
    ("cat", "litter"), ("cat", "accessories"), ("cat", "toys"),
    ("cat", "health"), ("cat", "grooming"),
    ("small_animal", "dry-food"), ("small_animal", "treats"),
    ("small_animal", "accessories"), ("small_animal", "toys"),
    ("small_animal", "health"),
    ("bird", "dry-food"), ("bird", "treats"), ("bird", "accessories"),
    ("bird", "toys"), ("bird", "health"),
    ("aquarium", "aquarium"), ("aquarium", "health"),
]

DIETARIES: list[str] = [
    "grain-free", "senior", "puppy", "large-breed",
    "sensitive", "indoor", "weight-control",
]

# Plausible dietary tags per (pet_type, category). Most foods carry
# a dietary; treats and accessories often do not.
DIETARY_BY_PET_CATEGORY: dict[tuple[str, str], list[str]] = {
    ("dog", "dry-food"):
        ["grain-free", "senior", "puppy", "large-breed", "sensitive", "weight-control"],
    ("dog", "wet-food"):
        ["grain-free", "senior", "puppy", "large-breed", "sensitive"],
    ("dog", "treats"):        ["grain-free", "puppy", "weight-control"],
    ("dog", "dental-treats"): ["grain-free"],
    ("cat", "dry-food"):
        ["grain-free", "senior", "indoor", "sensitive", "weight-control"],
    ("cat", "wet-food"):      ["grain-free", "senior", "indoor", "sensitive"],
    ("cat", "treats"):        ["grain-free", "indoor"],
    ("small_animal", "dry-food"): ["sensitive", "senior"],
    ("bird", "dry-food"):     [],
    ("aquarium", "aquarium"): [],
}

# Tax classes — three values keeps the Filling demo's confidence
# chips high (5-field multi-predict can comfortably hit p ≥ 0.85).
TAX_CLASSES: list[str] = ["food-reduced", "standard", "pharma"]

TAX_BY_CATEGORY: dict[str, str] = {
    "dry-food":       "food-reduced",
    "wet-food":       "food-reduced",
    "treats":         "food-reduced",
    "dental-treats":  "food-reduced",
    "litter":         "standard",
    "accessories":    "standard",
    "toys":           "standard",
    "grooming":       "standard",
    "health":         "pharma",
    "aquarium":       "standard",
}

# Customer segments and pet sizes
SEGMENTS: list[str] = [
    "dog_owner", "cat_owner", "multi_pet",
    "small_animal_owner", "aquarium_owner",
]
PET_SIZES: list[str] = ["small", "medium", "large"]
REGIONS: list[str] = [
    "helsinki", "espoo", "tampere", "oulu", "turku", "jyvaskyla",
]

# Segment → distribution over customers. Skewed dog-heavy because
# that's our largest set of demo moments.
SEGMENT_WEIGHTS: dict[str, float] = {
    "dog_owner":          0.42,
    "cat_owner":          0.28,
    "multi_pet":          0.16,
    "small_animal_owner": 0.08,
    "aquarium_owner":     0.06,
}

# Segment → which pet_types this segment buys for, with weights.
# multi_pet skews towards dog+cat with both well-represented.
SEGMENT_PET_TYPE_WEIGHTS: dict[str, dict[str, float]] = {
    "dog_owner":          {"dog": 0.97, "cat": 0.02, "small_animal": 0.01},
    "cat_owner":          {"cat": 0.97, "dog": 0.02, "small_animal": 0.01},
    "multi_pet":          {"dog": 0.50, "cat": 0.45, "small_animal": 0.05},
    "small_animal_owner": {"small_animal": 0.85, "bird": 0.10, "cat": 0.05},
    "aquarium_owner":     {"aquarium": 0.95, "cat": 0.05},
}

# A large-breed dog owner's cat-product probability — driven down to
# < 1 % so Smart Search rank-flip lands. We override the base
# segment weights when pet_size == "large".
LARGE_BREED_PET_TYPE_WEIGHTS: dict[str, float] = {
    "dog": 0.995, "cat": 0.003, "small_animal": 0.002,
}


# ── Persona customers (TASK.md For You + customer-switcher) ────────

@dataclass(frozen=True)
class Persona:
    customer_id: str
    name_hint: str       # for friendly logging only — not stored in fixture
    segment: str
    pet_size: str | None
    region: str
    tenure_months: int
    target_orders: int   # 8-14 hand-curated historical orders
    # Per-persona override for pet-type sampling. None means "use the
    # segment default". Olli has a heavy dog skew despite being
    # multi_pet so his top-5 (pet_type, category) pairs stay disjoint
    # from Maija's — see ADR 0002 §Engineered signal #3.
    pet_type_weights: dict[str, float] | None = None


PERSONAS: list[Persona] = [
    Persona("CUST-00001", "Maija",  "cat_owner",
            None,    "helsinki", tenure_months=18, target_orders=12),
    Persona("CUST-00002", "Olli",   "multi_pet",
            "small", "tampere",  tenure_months=9,  target_orders=10,
            # Heavily dog-leaning multi_pet. Keeps Maija ∩ Olli top-5
            # ≤ 1 shared pair while preserving the multi_pet flavour
            # (Olli still buys cat products occasionally).
            pet_type_weights={"dog": 0.85, "cat": 0.15}),
    Persona("CUST-00003", "Saara",  "dog_owner",
            "large", "espoo",    tenure_months=26, target_orders=14),
]


# ── Output dataclasses ──────────────────────────────────────────────

@dataclass
class Product:
    sku: str
    name: str
    category: str
    pet_type: str
    brand: str
    price_eur: float
    weight_kg: float | None = None
    dietary: str | None = None
    tax_class: str | None = None


@dataclass
class Customer:
    customer_id: str
    segment: str
    pet_size: str | None
    region: str
    tenure_months: int
    # Backfilled from orders in a post-pass. These columns power the
    # Churn view's `_predict churned` and the Dashboard's loyalty KPIs.
    # Stored on the customers table so Aito can condition on them
    # without a join. See ADR 0013.
    total_orders: int = 0
    total_spent_eur: float = 0.0
    last_order_month: str | None = None
    churned: bool = False


@dataclass
class Review:
    """Customer review of a product. Drives the Feedback view's
    multi-field `_predict` over the `text` Text column — category +
    sentiment + assigned_to + churn_within_90d from the review's
    text. See ADR 0012."""
    review_id: str
    customer_id: str
    product_sku: str
    rating: int        # 1-5
    text: str          # Text column, whitespace-analyzed
    category: str      # shipping / quality / fit / praise / question
    sentiment: str     # positive / negative / neutral
    assigned_to: str   # support-team member
    created_at: str    # YYYY-MM
    # Forward-looking label: True iff the customer has no orders in
    # the 3 months after this review. Backfilled in a post-pass once
    # we know each customer's last_order_month. Gives the Feedback
    # view a 4th `_predict` — "churn risk from text" — alongside
    # category / sentiment / assigned_to. See ADR 0013 §"Forward
    # labels".
    churn_within_90d: bool = False


@dataclass
class CustomerMonth:
    """Panel-data row: one per customer per month they were active.

    The training shape for proper time-series churn prediction —
    visits decay, latest review snapshot, this month's purchases +
    spend, profile features denormalised. The target column
    `churned_in_3_months` is the demo's forward-looking label: True
    iff the customer's last order is in or before this row's month.

    See ADR 0013 §"Panel data" for the design rationale.
    """
    customer_month_id: str          # "CUST-00001-2025-03"
    customer_id: str                # link → customers
    month: str                      # YYYY-MM
    visits: int                     # synthetic per-month site visits
    purchases: int                  # orders this month
    spent_eur: float                # sum of order totals this month
    segment: str                    # denormalised
    pet_size: str | None            # denormalised, nullable
    region: str                     # denormalised
    tenure_months_at_month: int     # months since first order at this row's month
    latest_rating: int | None       # most-recent review rating in this month
    latest_sentiment: str | None    # sentiment of that review
    latest_category: str | None     # category of that review
    churned_in_3_months: bool       # the forward target


@dataclass
class MonthlySale:
    """Per-SKU per-month sales aggregate. Powers the Demand
    Forecast view's `_predict units_sold` and the Inventory view's
    days-of-supply arithmetic. Denormalised pet_type + category +
    brand + season so Aito conditions in one hop without traversal
    back to products. See ADR 0014."""
    monthly_sale_id: str       # "SKU-PT-0001-2025-03"
    product_sku: str           # link → products.sku
    month: str                 # YYYY-MM
    units_sold: int
    revenue_eur: float
    unique_customers: int
    pet_type: str              # denormalised
    category: str              # denormalised
    brand: str                 # denormalised
    season: str                # "spring" | "summer" | "autumn" | "winter"


@dataclass
class InventoryRow:
    """Per-SKU stock snapshot at the frozen demo today (2026-04).
    Powers the Inventory Intelligence view's reorder workflow with
    cash-impact figures. Stock values are synthesised — not from a
    real WMS — but the arithmetic (days-of-supply, reorder triggers,
    tied capital, revenue at risk) matches a real merchandising
    operation. See ADR 0015."""
    sku: str                       # link → products.sku
    current_stock: int
    unit_cost_eur: float           # ≈ 60 % of retail price
    lead_time_days: int            # 7-28 by category
    reorder_point: int             # lead-time demand + safety stock
    safety_stock: int              # ~1 week buffer
    supplier: str                  # "S-01" … "S-12"
    last_received_month: str       # most recent restock month


@dataclass
class PriceObservation:
    """Per-SKU per-month price snapshot. Powers the Price
    Intelligence view's fair-band computation + Aito's `_relate`
    over price-band ↔ units_sold sweet spots. Synthesised from
    list price with occasional promotional drops. See ADR 0016."""
    price_observation_id: str      # "SKU-PT-0001-2025-03"
    product_sku: str               # link → products.sku
    month: str
    price_eur: float
    list_price_eur: float          # the SKU's current retail price
    discount_pct: float            # (list_price - price) / list_price × 100


@dataclass
class Order:
    order_id: str
    customer_id: str
    month: str          # YYYY-MM
    total_eur: float
    # Denormalised: space-separated `<pet_type>__<category>` tokens
    # for every line in this order. Lets Aito's `_relate from
    # orders where {line_categories: {$match: "dog__dry-food"}} relate
    # line_categories` do order-level co-occurrence directly, without
    # a join-via-reverse-link that Aito's `_relate` doesn't expose.
    # See ADR 0008.
    line_categories: str = ""


@dataclass
class OrderLine:
    line_id: str
    order_id: str
    product_sku: str
    qty: int
    returned: bool
    # Denormalised mirror of `orders.customer_id.{segment, pet_size}`.
    # Aito's `_recommend` / `_predict` / `_relate` from `order_lines`
    # only do single-hop link traversal — they can reach
    # `order_id.<orders col>` and `product_sku.<products col>` but
    # not two-hop into `order_id.customer_id.<customers col>`. Pulling
    # the two demo-load-bearing customer attributes down to the line
    # level lets Smart Search bias by segment + pet_size without a
    # client-side join. See ADR 0006.
    customer_segment: str
    customer_pet_size: str | None = None


# ── Generation ──────────────────────────────────────────────────────

def _round_eur(x: float) -> float:
    """Two-decimal rounding so JSON output is stable across runs."""
    return round(x, 2)


def gen_products(rng: random.Random) -> list[Product]:
    """Generate ~700 products spanning every plausible
    (brand, pet_type, category) combination, with name variations
    so token overlap on `_search` is realistic.
    """
    products: list[Product] = []
    counter = 1

    def make_sku() -> str:
        nonlocal counter
        sku = f"SKU-PT-{counter:04d}"
        counter += 1
        return sku

    # Product name fragments by category. "{brand} {dietary?} {variant} {size?}"
    SIZE_VARIANTS_KG = {
        "dry-food":      [1, 2, 4, 7, 12, 15],
        "wet-food":      [0.085, 0.150, 0.4],
        "treats":        [0.1, 0.2, 0.5],
        "dental-treats": [0.08, 0.12, 0.2],
        "litter":        [5, 7, 12],
        "aquarium":      [None],
        "accessories":   [None],
        "toys":          [None],
        "grooming":      [None],
        "health":        [None],
    }

    FLAVOURS_BY_PET_CAT: dict[tuple[str, str], list[str]] = {
        ("dog", "dry-food"):      ["Chicken", "Lamb", "Salmon", "Beef", "Turkey"],
        ("dog", "wet-food"):      ["Chicken", "Lamb", "Beef", "Turkey", "Duck"],
        ("dog", "treats"):        ["Bacon", "Liver", "Cheese", "Mixed Reward"],
        ("dog", "dental-treats"): ["Daily Dental", "Puppy Dental", "Fresh Breath"],
        ("dog", "accessories"):   ["Collar", "Leash", "Harness", "Bowl", "Travel Carrier"],
        ("dog", "toys"):          ["Tug Rope", "Squeak Ball", "Chew Bone", "Tennis Ball"],
        ("dog", "health"):        ["Joint Care", "Dental Spray", "Ear Cleaner", "Calming Tablets"],
        ("dog", "grooming"):      ["Shampoo", "Brush", "Nail Clipper"],
        ("cat", "dry-food"):      ["Salmon", "Tuna", "Chicken", "Turkey", "Whitefish"],
        ("cat", "wet-food"):      ["Tuna", "Salmon", "Chicken", "Beef", "Liver"],
        ("cat", "treats"):        ["Tuna Sticks", "Crunchy Bites", "Salmon Drops"],
        ("cat", "litter"):        ["Clumping Clay", "Silica Crystals", "Recycled Paper"],
        ("cat", "accessories"):   ["Scratching Post", "Bowl", "Water Fountain", "Carrier"],
        ("cat", "toys"):          ["Feather Wand", "Catnip Mouse", "Laser Pointer"],
        ("cat", "health"):        ["Hairball Paste", "Calming Diffuser", "Flea Drops"],
        ("cat", "grooming"):      ["Shampoo", "Brush", "Nail Clipper"],
        ("small_animal", "dry-food"):     ["Rabbit Pellets", "Guinea Pig Mix", "Hamster Mix"],
        ("small_animal", "treats"):       ["Veggie Crunch", "Hay Sticks", "Fruit Drops"],
        ("small_animal", "accessories"):  ["Cage", "Water Bottle", "Hideout"],
        ("small_animal", "toys"):         ["Wooden Chew", "Exercise Wheel", "Tunnel"],
        ("small_animal", "health"):       ["Vitamin Drops", "Mite Treatment"],
        ("bird", "dry-food"):  ["Parrot Mix", "Canary Seed", "Budgie Blend"],
        ("bird", "treats"):    ["Honey Stick", "Millet Spray"],
        ("bird", "accessories"): ["Perch", "Feeder", "Cage Cover"],
        ("bird", "toys"):      ["Swing", "Mirror", "Bell Toy"],
        ("bird", "health"):    ["Feather Spray", "Beak Conditioner"],
        ("aquarium", "aquarium"): [
            "Filter Pads", "Water Conditioner", "Aquatic Plants",
            "Tropical Flakes", "Cichlid Pellets", "Algae Wafers",
            "Tank Heater", "Air Pump",
        ],
        ("aquarium", "health"): ["Anti-Fungal Drops", "pH Adjuster"],
    }

    for pet_type, category in PET_CATEGORY_PAIRS:
        eligible_brands = [
            b for b, pet_cats in BRAND_CATEGORIES.items()
            if category in pet_cats.get(pet_type, [])
        ]
        flavours = FLAVOURS_BY_PET_CAT.get((pet_type, category), ["Standard"])
        sizes = SIZE_VARIANTS_KG.get(category, [None])
        dietaries = DIETARY_BY_PET_CATEGORY.get((pet_type, category), [])

        for brand in eligible_brands:
            for flavour in flavours:
                # Variant count tuned so the total catalog lands in the
                # 600-800 SKU band from TASK.md. Food categories get
                # more variants because real shops sell each flavour
                # in multiple bag sizes / dietary lines.
                if category in FILLABLE_CATEGORIES:
                    n_variants = rng.choices([3, 4, 5, 6], weights=[0.25, 0.45, 0.20, 0.10])[0]
                else:
                    n_variants = rng.choices([1, 2, 3], weights=[0.5, 0.4, 0.1])[0]
                for _ in range(n_variants):
                    weight = rng.choice(sizes)
                    dietary: str | None = (
                        rng.choice(dietaries) if dietaries and rng.random() < 0.65
                        else None
                    )
                    name = _compose_name(brand, flavour, dietary, weight, category, pet_type)
                    base_price = _base_price(category, weight)
                    price = _round_eur(base_price * rng.uniform(0.92, 1.12))
                    tax_class = TAX_BY_CATEGORY.get(category, "standard")

                    products.append(Product(
                        sku=make_sku(),
                        name=name,
                        category=category,
                        pet_type=pet_type,
                        brand=brand,
                        price_eur=price,
                        weight_kg=weight,
                        dietary=dietary,
                        tax_class=tax_class,
                    ))

    # ── Signal #4: Product Filling input pile ──────────────────────
    #
    # The Filling demo shows products like "Acana Large Breed Adult"
    # — a dry-food item that *should* carry weight + dietary +
    # tax_class but doesn't. Only foody categories naturally carry
    # all three; for accessories/toys/grooming/health/aquarium,
    # weight_kg and dietary aren't meaningful and a "missing" field
    # there isn't really missing.
    #
    # So we (a) restrict the candidate pool to FILLABLE_CATEGORIES,
    # (b) ensure every candidate currently has all three fields
    # populated (re-fill any nullable ones first), then (c) null
    # exactly two of three fields on 5 % of THAT pool.
    #
    # The signal-validation test counts products in the candidate
    # pool with ≥ 2 nulls and asserts it's in the 4–6 % band.
    candidate_idxs = [
        i for i, p in enumerate(products)
        if p.category in FILLABLE_CATEGORIES
    ]
    # Make sure every candidate has all three fields populated
    # going in; we only want the deliberate nulls to count.
    for i in candidate_idxs:
        p = products[i]
        if p.dietary is None:
            options = DIETARY_BY_PET_CATEGORY.get((p.pet_type, p.category), [])
            if options:
                p.dietary = rng.choice(options)
        if p.weight_kg is None:
            sizes = SIZE_VARIANTS_KG.get(p.category, [None])
            non_null_sizes = [s for s in sizes if s is not None]
            if non_null_sizes:
                p.weight_kg = rng.choice(non_null_sizes)
        if p.tax_class is None:
            p.tax_class = TAX_BY_CATEGORY.get(p.category, "standard")

    fillable_after_repair = [
        i for i in candidate_idxs
        if products[i].weight_kg is not None
        and products[i].dietary is not None
        and products[i].tax_class is not None
    ]
    fill_count = max(1, round(len(fillable_after_repair) * 0.05))
    fill_targets = rng.sample(fillable_after_repair, k=fill_count)
    for idx in fill_targets:
        # Null exactly two of three fields per ADR 0002 #4.
        candidates = ["weight_kg", "dietary", "tax_class"]
        nulled = rng.sample(candidates, k=2)
        p = products[idx]
        if "weight_kg" in nulled:
            p.weight_kg = None
        if "dietary" in nulled:
            p.dietary = None
        if "tax_class" in nulled:
            p.tax_class = None

    return products


# Categories where the Filling demo's "missing fields" framing is
# meaningful — i.e. where weight_kg, dietary, and tax_class are all
# normally populated. Used by the null-injection step in `gen_products`
# and by the signal #4 test.
FILLABLE_CATEGORIES: set[str] = {
    "dry-food", "wet-food", "treats", "dental-treats", "litter",
}


def _compose_name(brand: str, flavour: str, dietary: str | None,
                  weight: float | None, category: str, pet_type: str) -> str:
    """Produce a readable, search-tokenisable product name.

    Names include the food/care vocabulary buyers actually search for —
    "food", "treats", "litter" — so Smart Search has natural tokens
    to bind on.
    """
    parts: list[str] = [brand]
    if dietary:
        parts.append(dietary.replace("-", " ").title())
    parts.append(flavour)
    # Append an explicit word that matches how a shopper searches.
    if category in ("dry-food", "wet-food"):
        # "dog/cat food" plus the kind. "Whiskas Salmon Cat Food 2kg".
        if pet_type == "dog":
            parts.append("Dog Food")
        elif pet_type == "cat":
            parts.append("Cat Food")
        else:
            parts.append("Food")
    elif category == "dental-treats":
        parts.append("Dental Treats")
    elif category == "treats":
        parts.append("Treats")
    elif category == "litter":
        parts.append("Cat Litter")
    elif category == "aquarium":
        # Flavour is the product itself ("Filter Pads")
        pass
    else:
        # accessories, toys, grooming, health — the flavour already
        # includes the noun ("Collar", "Squeak Ball", "Brush").
        pass
    if weight is not None:
        if weight < 1:
            parts.append(f"{int(weight * 1000)}g")
        else:
            parts.append(f"{weight:g}kg")
    return " ".join(parts)


def _base_price(category: str, weight_kg: float | None) -> float:
    base_per_kg = {
        "dry-food":       6.5,
        "wet-food":      11.0,
        "treats":        18.0,
        "dental-treats": 22.0,
        "litter":         1.6,
    }
    if category in base_per_kg and weight_kg:
        return base_per_kg[category] * weight_kg
    if category == "accessories":  return 19.9
    if category == "toys":         return 12.5
    if category == "grooming":     return 14.5
    if category == "health":       return 18.0
    if category == "aquarium":     return 24.0
    return 9.9


def gen_customers(rng: random.Random) -> list[Customer]:
    """Generate ~3000 customers. The three named personas (Maija /
    Olli / Saara) get fixed ids `CUST-00001..3` so the For You
    customer-switcher in the UI hits stable rows.
    """
    customers: list[Customer] = []

    for p in PERSONAS:
        customers.append(Customer(
            customer_id=p.customer_id,
            segment=p.segment,
            pet_size=p.pet_size,
            region=p.region,
            tenure_months=p.tenure_months,
        ))

    # Algorithmic crowd — 3000 - len(personas) more.
    for i in range(len(PERSONAS) + 1, 3001):
        cid = f"CUST-{i:05d}"
        segment = rng.choices(SEGMENTS, weights=[SEGMENT_WEIGHTS[s] for s in SEGMENTS])[0]
        pet_size: str | None = None
        if segment in ("dog_owner", "multi_pet"):
            # Multi_pet dogs lean small/medium; dog_owner skews towards medium/large.
            if segment == "dog_owner":
                pet_size = rng.choices(PET_SIZES, weights=[0.18, 0.42, 0.40])[0]
            else:
                pet_size = rng.choices(PET_SIZES, weights=[0.55, 0.35, 0.10])[0]
        region = rng.choices(REGIONS, weights=[0.32, 0.18, 0.18, 0.10, 0.12, 0.10])[0]
        # Tenure log-skewed — most customers acquired in the last year.
        tenure = int(rng.expovariate(1 / 11)) + 1
        tenure = min(tenure, 28)
        customers.append(Customer(cid, segment, pet_size, region, tenure))

    return customers


def _candidate_products(
    products: list[Product],
    pet_type: str,
    category_bias: dict[str, float] | None = None,
) -> list[Product]:
    """All products of the right pet_type, biased toward `category_bias`."""
    return [p for p in products if p.pet_type == pet_type]


def _pick_product(
    rng: random.Random,
    products_by_pet: dict[str, list[Product]],
    pet_type: str,
    category_bias: dict[str, float] | None = None,
) -> Product:
    """Pick a product of `pet_type`, weighted by category_bias."""
    pool = products_by_pet[pet_type]
    if not pool:
        # Should not happen if products span every pet_type — but if it
        # does, fall back to any product so the generator never deadlocks.
        return rng.choice(next(iter(products_by_pet.values())))
    if category_bias is None:
        return rng.choice(pool)
    weights = [category_bias.get(p.category, 0.05) for p in pool]
    return rng.choices(pool, weights=weights, k=1)[0]


def _category_bias(segment: str, pet_size: str | None) -> dict[str, float]:
    """Per-segment category preference, with a large-breed twist
    pushing small/indoor products down."""
    if segment in ("dog_owner", "multi_pet"):
        # Dental-treats deliberately omitted: they're injected ONLY
        # through the conditional boost in `gen_orders_and_lines`
        # (when the order contains dog dry-food). And dry-food itself
        # is held to ~16 % of line picks so that
        #   P(dryfood-dog appears in a random order) is small,
        #   P(dental-treats | dryfood-dog) ≈ boost rate (high),
        # which lets `_relate` lift on the demo path land near 3×.
        # Treats / wet-food / accessories soak up the rest of the
        # mix so dog customers still look like dog customers.
        return {
            "dry-food":    0.13,
            "wet-food":    0.22,
            "treats":      0.24,
            "accessories": 0.19,
            "toys":        0.10,
            "health":      0.06,
            "grooming":    0.06,
        }
    if segment == "cat_owner":
        return {
            "wet-food":      0.30,
            "dry-food":      0.22,
            "litter":        0.18,
            "treats":        0.12,
            "accessories":   0.08,
            "health":        0.05,
            "grooming":      0.03,
            "toys":          0.02,
        }
    if segment == "small_animal_owner":
        return {
            "dry-food":    0.38,
            "treats":      0.24,
            "accessories": 0.18,
            "toys":        0.12,
            "health":      0.08,
        }
    if segment == "aquarium_owner":
        return {"aquarium": 0.92, "health": 0.08}
    return {}


def _segment_pet_type_weights(segment: str, pet_size: str | None) -> dict[str, float]:
    base = SEGMENT_PET_TYPE_WEIGHTS[segment]
    if segment == "dog_owner" and pet_size == "large":
        return LARGE_BREED_PET_TYPE_WEIGHTS
    return base


def _orders_per_customer(rng: random.Random, c: Customer) -> int:
    """Decide how many orders this customer placed in the 24 month window.

    Tenure caps the upper bound (a customer acquired 2 months ago can't
    have 30 orders). Heavy-tailed: most customers ≤ 3 orders, a long
    tail has > 10.
    """
    cap = max(2, c.tenure_months // 2 + 3)
    raw = int(rng.expovariate(1 / 6.5))
    return max(1, min(raw, cap, 22))


# Twenty-four month window: 2024-05 .. 2026-04 (inclusive).
_MONTH_WINDOW: list[str] = [
    f"{y:04d}-{m:02d}"
    for y, m in [
        (y, m)
        for y in (2024, 2025, 2026)
        for m in range(1, 13)
    ]
    if (y, m) >= (2024, 5) and (y, m) <= (2026, 4)
]

# Frozen "today" — every recency calculation reads from this anchor
# so the demo's numbers (churn rate, "active in last 90 days") stay
# stable across reloads. Mirrors `aito-accounting-demo`'s
# `date_window.py` pattern.
DEMO_TODAY_YYYYMM = "2026-04"

# A customer counts as churned if their last order is in or before
# this month. 90 days = 3 months at month resolution; cutoff =
# 2026-01 ⇒ "no orders in Feb / Mar / Apr 2026". ADR 0013 §"Window".
CHURN_CUTOFF_YYYYMM = "2026-01"

# Where churning customers' orders cluster — 5+ months before today,
# unambiguously past the cutoff. The two-month gap between
# CHURN_WINDOW_MAX and CHURN_CUTOFF_YYYYMM stops random month picks
# from straddling the boundary.
CHURN_WINDOW_MAX = "2025-11"


def _churn_propensity(customer: "Customer", n_orders: int) -> float:
    """P(this customer is churning), driven by feature contributions.

    The "drivers" in this function are what the Churn view's `_relate
    churned=true` query surfaces — short tenure brushed off as "too
    new to churn", long tenure as "had time to drift", segment +
    region effects. Tuned so the overall churn rate lands in the
    20-30 % band: high enough that the demo has a meaningful at-risk
    cohort, low enough that the headline is "most customers stay".
    """
    p = 0.04                                    # base rate
    if customer.tenure_months > 18:    p += 0.04
    if customer.tenure_months < 4:     p -= 0.02
    if n_orders <= 3:                  p += 0.04
    # Segment + region contributions are deliberately strong so
    # `_relate churned=true relate {segment, region}` surfaces clear
    # drivers (≥ 1.3× lift on the top values). Without these the
    # effects wash out under the dominant tenure / low-orders bump.
    if customer.segment == "small_animal_owner":  p += 0.28
    if customer.segment == "aquarium_owner":      p += 0.22
    if customer.segment == "cat_owner":           p -= 0.06
    if customer.region == "oulu":                 p += 0.22
    if customer.region == "jyvaskyla":            p += 0.10
    if customer.region == "helsinki":             p -= 0.06
    if customer.region == "turku":                p -= 0.04
    return max(0.01, min(0.60, p))


# Per-segment baseline visit rate (sessions per month) for an active
# customer. Higher for multi-pet households (more "exploring"), lower
# for aquarium owners (single niche). Synthesized — not from a real
# analytics source. Drives the customer_months `visits` column.
_BASE_VISITS_BY_SEGMENT: dict[str, int] = {
    "dog_owner":          12,
    "cat_owner":           9,
    "multi_pet":          14,
    "small_animal_owner":  6,
    "aquarium_owner":      5,
}


def _months_between(start_yyyymm: str, end_yyyymm: str) -> int:
    """Number of full months from start to end (end - start)."""
    sy, sm = (int(x) for x in start_yyyymm.split("-"))
    ey, em = (int(x) for x in end_yyyymm.split("-"))
    return (ey - sy) * 12 + (em - sm)


def _add_months(yyyymm: str, n: int) -> str:
    """`yyyymm + n` at month resolution."""
    y, m = (int(x) for x in yyyymm.split("-"))
    total = y * 12 + (m - 1) + n
    ny, nm = divmod(total, 12)
    return f"{ny:04d}-{nm + 1:02d}"


def _decay_factor(is_churning: bool, month: str, last_order_month: str | None) -> float:
    """Visit-rate multiplier for churning customers near their last
    order month.

    Active (non-churning) customers don't decay — they're not
    stopping, just at their current cadence. Churning customers'
    visits taper over the 2 months before their last order and drop
    to near-zero after.
    """
    if not is_churning or last_order_month is None:
        return 1.0
    offset = _months_between(last_order_month, month)
    if offset <= -3: return 1.0      # still in normal-activity period
    if offset == -2: return 0.75
    if offset == -1: return 0.50
    if offset == 0:  return 0.30     # the last-order month itself
    if offset == 1:  return 0.10
    return 0.04                      # long after stopped


def _is_churning(customer: "Customer", n_orders: int) -> bool:
    """Deterministic churn-disposition decision per customer.

    Uses a sub-RNG seeded from the customer_id so the call doesn't
    perturb the main fixture RNG sequence — keeps the dog-food→
    dental lift, persona overlaps, and other engineered signals
    byte-identical across re-runs. Personas are never churned (they
    drive the For You demo and have to stay active).
    """
    if customer.customer_id in {p.customer_id for p in PERSONAS}:
        return False
    seed = sum(ord(c) for c in customer.customer_id)
    sub_rng = random.Random(seed)
    return sub_rng.random() < _churn_propensity(customer, n_orders)


def gen_orders_and_lines(
    rng: random.Random,
    customers: list[Customer],
    products: list[Product],
) -> tuple[list[Order], list[OrderLine]]:
    """Generate orders + lines with the engineered signal baked in.

    Signal strategy — see ADR 0002 §Engineered signal:

      1. Cat-product share for large-breed dog owners: enforced by
         `LARGE_BREED_PET_TYPE_WEIGHTS` (cat ≈ 0.3 %).
      2. Dog-food → dental-treats lift: when an order for a
         dog/multi-pet customer contains dry-food + a dog product,
         we add a dental-treat with P=0.35. Baseline P(dental-treat
         in any order) stays ~0.10. Lift ≈ 3.2.
      3. Maija/Olli/Saara persona orders are hand-curated by the
         same generator, but with their dedicated category-bias
         table to guarantee disjoint top-5 (pet_type, category) pairs.
      4. 5 % of products are nulled on attribute fields (in
         `gen_products`).
      5. ~3 % of order_lines have `returned=true`.
    """
    orders: list[Order] = []
    lines: list[OrderLine] = []
    order_counter = 1
    line_counter = 1

    products_by_pet: dict[str, list[Product]] = {pt: [] for pt in PET_TYPES}
    for p in products:
        products_by_pet[p.pet_type].append(p)

    # Persona orders first so they get the lowest ids (CUST-00001's
    # orders are ORD-00001..). Nice for debugging in the JSON.
    persona_ids = {p.customer_id: p for p in PERSONAS}

    for customer in customers:
        persona = persona_ids.get(customer.customer_id)
        if persona is not None:
            n_orders = persona.target_orders
        else:
            n_orders = _orders_per_customer(rng, customer)

        if persona is not None and persona.pet_type_weights is not None:
            pet_type_weights = persona.pet_type_weights
        else:
            pet_type_weights = _segment_pet_type_weights(customer.segment, customer.pet_size)
        cat_bias = _category_bias(customer.segment, customer.pet_size)

        # Pick the month window for this customer's orders. Churning
        # customers' orders cluster in months ≤ CHURN_WINDOW_MAX so
        # their `last_order_month` falls before the 90-day cutoff. The
        # decision is keyed off `customer.customer_id` (sub-RNG) so it
        # doesn't perturb the main RNG sequence — the persona overlaps,
        # dog-food→dental lift, etc. all stay byte-identical.
        eligible_months = _MONTH_WINDOW[-(customer.tenure_months + 1):]
        if _is_churning(customer, n_orders):
            churn_eligible = [m for m in eligible_months if m <= CHURN_WINDOW_MAX]
            # If a customer is too new for the churn window to overlap
            # their tenure-bounded month range, fall back to active —
            # they're literally too new to have churned.
            if churn_eligible:
                eligible_months = churn_eligible

        for _ in range(n_orders):
            order_id = f"ORD-{order_counter:05d}"
            order_counter += 1
            month = rng.choice(eligible_months)

            # 1-6 lines, mode at 2-3.
            n_lines = rng.choices(
                [1, 2, 3, 4, 5, 6],
                weights=[0.12, 0.30, 0.28, 0.18, 0.08, 0.04],
            )[0]

            order_skus: set[str] = set()
            this_orders_lines: list[OrderLine] = []
            order_total = 0.0

            for _line_i in range(n_lines):
                # Pick a pet_type for this line, then a category-biased product.
                pet_type = rng.choices(
                    list(pet_type_weights.keys()),
                    weights=list(pet_type_weights.values()),
                )[0]
                if not products_by_pet[pet_type]:
                    pet_type = rng.choice(list(products_by_pet.keys()))
                product = _pick_product(rng, products_by_pet, pet_type, cat_bias)
                if product.sku in order_skus:
                    continue
                order_skus.add(product.sku)
                qty = rng.choices([1, 2, 3], weights=[0.78, 0.18, 0.04])[0]
                returned = rng.random() < 0.03
                line = OrderLine(
                    line_id=f"LN-{line_counter:06d}",
                    order_id=order_id,
                    product_sku=product.sku,
                    qty=qty,
                    returned=returned,
                    customer_segment=customer.segment,
                    customer_pet_size=customer.pet_size,
                )
                line_counter += 1
                this_orders_lines.append(line)
                order_total += product.price_eur * qty

            # ── Signal #2: dog-food → dental-treats co-occurrence ───
            #
            # If this order is from a dog-leaning customer and contains
            # a dog dry-food line, add a dental-treats line with P=0.35.
            # Baseline P(dental-treat) is ~0.10; this drives lift ≈ 3.2
            # under the condition.
            if customer.segment in ("dog_owner", "multi_pet"):
                has_dog_dryfood = any(
                    _sku_to_product(products, ln.product_sku).category == "dry-food"
                    and _sku_to_product(products, ln.product_sku).pet_type == "dog"
                    for ln in this_orders_lines
                )
                if has_dog_dryfood and rng.random() < 0.70:
                    dental_pool = [
                        p for p in products_by_pet["dog"]
                        if p.category == "dental-treats" and p.sku not in order_skus
                    ]
                    if dental_pool:
                        product = rng.choice(dental_pool)
                        qty = rng.choices([1, 2], weights=[0.85, 0.15])[0]
                        returned = rng.random() < 0.02  # dental treats rarely returned
                        line = OrderLine(
                            line_id=f"LN-{line_counter:06d}",
                            order_id=order_id,
                            product_sku=product.sku,
                            qty=qty,
                            returned=returned,
                            customer_segment=customer.segment,
                            customer_pet_size=customer.pet_size,
                        )
                        line_counter += 1
                        this_orders_lines.append(line)
                        order_total += product.price_eur * qty

            if not this_orders_lines:
                # Edge case: every line we tried collided. Skip the
                # order rather than ship an order with zero lines.
                order_counter -= 1
                continue

            lines.extend(this_orders_lines)
            # Build the denormalised `line_categories` Text field from
            # each line's product. Aito tokenises Text on whitespace
            # AND on hyphens, so `dry-food` would split into `dry`
            # and `food`. We strip hyphens from category names when
            # forming the token (`dry-food` → `dryfood`,
            # `dental-treats` → `dentaltreats`), keeping each
            # (pet_type, category) pair as one indivisible token.
            line_tokens: list[str] = []
            for ln in this_orders_lines:
                prod = _sku_to_product(products, ln.product_sku)
                clean_cat = prod.category.replace("-", "")
                line_tokens.append(f"{prod.pet_type}_{clean_cat}")
            orders.append(Order(
                order_id=order_id,
                customer_id=customer.customer_id,
                month=month,
                total_eur=_round_eur(order_total),
                line_categories=" ".join(line_tokens),
            ))

    return orders, lines


# Linear scan — fine for fixture generation (we run it once per regen).
# Avoids dragging in a global lookup we don't need at runtime.
def _sku_to_product(products: list[Product], sku: str) -> Product:
    for p in products:
        if p.sku == sku:
            return p
    raise KeyError(sku)


# ── Customer aggregates (post-pass after orders) ────────────────────


def backfill_customer_aggregates(
    customers: list[Customer],
    orders: list[Order],
) -> None:
    """Populate total_orders, total_spent_eur, last_order_month, churned.

    Aito needs these as customer-level columns so `_predict churned`
    and `_relate churned=true` can condition on them without a join.
    Computed in a single pass over orders after they're generated —
    the values are derived data, not engineered noise.

    `churned` is the deterministic label: last_order_month ≤
    CHURN_CUTOFF_YYYYMM. The `_is_churning` decision earlier already
    biased the month distribution; this pass converts that into the
    column the schema exposes.
    """
    totals: dict[str, int] = {}
    spent: dict[str, float] = {}
    last_month: dict[str, str] = {}
    for o in orders:
        cid = o.customer_id
        totals[cid] = totals.get(cid, 0) + 1
        spent[cid] = spent.get(cid, 0.0) + o.total_eur
        prev = last_month.get(cid)
        if prev is None or o.month > prev:
            last_month[cid] = o.month
    for c in customers:
        c.total_orders = totals.get(c.customer_id, 0)
        c.total_spent_eur = _round_eur(spent.get(c.customer_id, 0.0))
        c.last_order_month = last_month.get(c.customer_id)
        c.churned = bool(
            c.last_order_month is not None
            and c.last_order_month <= CHURN_CUTOFF_YYYYMM
        )


# ── Reviews ────────────────────────────────────────────────────────


# Five problem/feedback categories. Each maps 1:1 to a support
# team-member assignment so Aito's `_predict assigned_to` has a strong
# learnable signal off `category` (and indirectly off `text`).
REVIEW_CATEGORIES: list[str] = ["shipping", "quality", "fit", "praise", "question"]
REVIEW_CATEGORY_TO_AGENT: dict[str, str] = {
    "shipping": "Anna",    # logistics
    "quality":  "Petri",   # product team
    "fit":      "Maria",   # returns / exchanges
    "praise":   "Joonas",  # marketing / social
    "question": "Sari",    # customer support
}

# Per-category template bank. Slot keys are filled from the vocab map
# below; each template fills exactly one or two slots. Templates are
# distinct enough that token overlap across categories is rare —
# Aito's `_predict category` from `text` hits 80–90 % accuracy on the
# generated data.
_REVIEW_TEMPLATES: dict[str, list[str]] = {
    "shipping": [
        "Package arrived {timing}. {detail}.",
        "Delivery took {timing} — {detail}.",
        "Shipping was {timing}, packaging {pack_quality}.",
        "Order shipped {timing}; box {pack_quality}.",
        "Took {timing} for delivery. {detail}.",
        "{detail}. Shipping was {timing}.",
    ],
    "quality": [
        "The {product_noun} smells {scent} and my {pet} {reaction}.",
        "Quality is {quality_adj}. {detail}.",
        "Looks {quality_adj} compared to the listing photo.",
        "{detail}. Would {action} again.",
        "Contents are {quality_adj}. {detail}.",
        "Material feels {quality_adj}. {detail}.",
    ],
    "fit": [
        "Bought size {size} but it runs {fit_adj}.",
        "Sizing chart is {accuracy_adj}. {detail}.",
        "Size {size} fits my {pet} {fit_adj}.",
        "Returned for a different size — {detail}.",
        "The {size} is {fit_adj} for my {pet}.",
    ],
    "praise": [
        "{pet} loves it. {detail}.",
        "Best {product_noun} we have tried. {detail}.",
        "Great {feature}. {detail}.",
        "{pet} cannot get enough of these.",
        "Five stars — {detail}.",
        "{pet} approves. {detail}.",
    ],
    "question": [
        "Does this {question_clause}?",
        "Is the {product_noun} suitable for {pet}s with {condition}?",
        "Can I {question_clause}?",
        "Wondering if {question_clause}?",
        "Question — {question_clause}?",
    ],
}

_REVIEW_VOCAB: dict[str, list[str]] = {
    "timing":         ["quickly", "fast", "slowly", "late", "on time", "two days late"],
    "pack_quality":   ["intact", "dented", "torn", "sealed properly", "damaged"],
    "detail": [
        "no issues", "the seal was broken", "tracking was helpful",
        "the box arrived crushed", "everything was as described",
        "very satisfied", "minor packaging damage", "label was unreadable",
    ],
    "product_noun":   ["bag", "treat", "kibble", "food", "litter", "toy"],
    "scent":          ["fresh", "off", "neutral", "fishy", "pleasant"],
    "pet":            ["dog", "cat", "puppy", "kitten", "rabbit"],
    "reaction":       ["loved it", "would not eat it", "tried one piece then walked away",
                       "ate the whole thing", "got upset stomach"],
    "quality_adj":    ["excellent", "poor", "decent", "great", "below expectations", "premium"],
    "action":         ["buy", "recommend", "order", "skip"],
    "size":           ["S", "M", "L", "XL"],
    "fit_adj":        ["too small", "too large", "perfectly", "snug", "loose"],
    "accuracy_adj":   ["accurate", "off by one size", "confusing", "spot-on"],
    "feature":        ["flavour", "smell", "packaging", "texture", "ingredients", "value"],
    "question_clause": [
        "work for senior dogs",
        "be safe for puppies",
        "contain grain",
        "fit a large breed",
        "be used in an aquarium with shrimp",
        "be combined with wet food",
    ],
    "condition":      ["allergies", "sensitive stomach", "diabetes", "joint issues", "anxiety"],
}

# Category share — slightly praise-heavy to mirror real review
# distributions (most reviews are positive), with enough shipping +
# quality complaints to give the support team real triage volume.
_REVIEW_CATEGORY_WEIGHTS: dict[str, float] = {
    "praise":   0.40,
    "quality":  0.22,
    "shipping": 0.18,
    "fit":      0.10,
    "question": 0.10,
}

_RATING_BY_CATEGORY: dict[str, dict[int, float]] = {
    "praise":   {5: 0.65, 4: 0.30, 3: 0.05},
    "quality":  {1: 0.20, 2: 0.30, 3: 0.30, 4: 0.15, 5: 0.05},
    "shipping": {1: 0.25, 2: 0.35, 3: 0.30, 4: 0.08, 5: 0.02},
    "fit":      {1: 0.15, 2: 0.30, 3: 0.35, 4: 0.15, 5: 0.05},
    "question": {3: 0.50, 4: 0.30, 5: 0.10, 2: 0.07, 1: 0.03},
}


def _sentiment_for(rating: int) -> str:
    if rating >= 4: return "positive"
    if rating <= 2: return "negative"
    return "neutral"


def gen_reviews(
    rng: random.Random,
    products: list[Product],
    customers: list[Customer],
    orders: list[Order],
    lines: list[OrderLine],
) -> list[Review]:
    """Generate ~6000 customer reviews tied to actual order lines.

    Every review is anchored on a real `(customer_id, product_sku)`
    pair from the line history — so the Aito panel can show "this
    review is from a real customer about a real product" without
    inventing relationships.

    Volume rationale: 6000 reviews across ~30 templates lands at
    ~200 supporting cases per template, which is what makes the
    Feedback view's `$why` factors tight — Aito's lift values
    stabilise once each pattern has hundreds of supporting cases.
    Fewer reviews = noisier `$why`, less authoritative explanations.

    Category distribution roughly matches real e-commerce review
    distributions (~40 % praise, 30-40 % product/shipping complaints,
    10-15 % questions). Rating distribution is conditioned on
    category so positive categories cluster on 4-5★ and complaint
    categories cluster on 1-3★ — gives the demo's `_predict
    sentiment` query a learnable signal that *isn't* just keyword
    matching on the text.
    """
    reviews: list[Review] = []
    sku_to_pet: dict[str, str] = {p.sku: p.pet_type for p in products}
    sku_to_cat: dict[str, str] = {p.sku: p.category for p in products}
    order_to_customer: dict[str, str] = {o.order_id: o.customer_id for o in orders}
    order_to_month: dict[str, str] = {o.order_id: o.month for o in orders}

    # Pick ~6000 (customer, product) pairs from the line history.
    # Each line has a moderate probability of producing a review; the
    # per-customer cap stops one heavy buyer from monopolising the
    # set (we want pattern diversity, not 50 reviews from one person).
    per_customer: dict[str, int] = {}
    target = 6000
    review_counter = 1
    rng.shuffle(lines)  # shuffle so we don't bias toward early customers
    for ln in lines:
        if len(reviews) >= target:
            break
        cust = order_to_customer.get(ln.order_id)
        if cust is None or per_customer.get(cust, 0) >= 5:
            continue
        if rng.random() > 0.22:   # ~22 % of lines get a review
            continue

        pet = sku_to_pet.get(ln.product_sku, "pet")
        category = rng.choices(
            REVIEW_CATEGORIES,
            weights=[_REVIEW_CATEGORY_WEIGHTS[c] for c in REVIEW_CATEGORIES],
        )[0]
        rating_dist = _RATING_BY_CATEGORY[category]
        rating = rng.choices(
            list(rating_dist.keys()),
            weights=list(rating_dist.values()),
        )[0]

        # Pick a template and fill its slots from the vocab map. Some
        # slots (like {pet}) draw from the actual product context;
        # others draw randomly.
        template = rng.choice(_REVIEW_TEMPLATES[category])
        text = template
        for slot in ("timing", "pack_quality", "detail", "product_noun",
                     "scent", "reaction", "quality_adj", "action", "size",
                     "fit_adj", "accuracy_adj", "feature", "question_clause",
                     "condition"):
            placeholder = "{" + slot + "}"
            if placeholder in text:
                text = text.replace(placeholder, rng.choice(_REVIEW_VOCAB[slot]))
        if "{pet}" in text:
            text = text.replace("{pet}", pet)

        review_id = f"REV-{review_counter:05d}"
        review_counter += 1
        reviews.append(Review(
            review_id=review_id,
            customer_id=cust,
            product_sku=ln.product_sku,
            rating=rating,
            text=text,
            category=category,
            sentiment=_sentiment_for(rating),
            assigned_to=REVIEW_CATEGORY_TO_AGENT[category],
            created_at=order_to_month.get(ln.order_id, DEMO_TODAY_YYYYMM),
        ))
        per_customer[cust] = per_customer.get(cust, 0) + 1

    return reviews


# ── Customer-months panel + review churn label ─────────────────────


def backfill_review_churn_label(
    reviews: list[Review],
    customers: list[Customer],
) -> None:
    """Set `review.churn_within_90d` from the customer's overall churn
    status + the review's month.

    True iff the customer is churned overall (`customer.churned`) AND
    the review's month is at or after the customer's last order month
    — i.e., the review was written at the tail end of their activity,
    not when they were still buying afterwards.

    The text-to-churn signal Aito learns from this label is the
    Feedback view's "4th predict" — given a review's text, predict
    P(this reviewer is on their way out).
    """
    by_id = {c.customer_id: c for c in customers}
    for r in reviews:
        c = by_id.get(r.customer_id)
        if c is None or not c.churned or c.last_order_month is None:
            r.churn_within_90d = False
            continue
        r.churn_within_90d = r.created_at >= c.last_order_month


def gen_customer_months(
    rng: random.Random,
    customers: list[Customer],
    orders: list[Order],
    reviews: list[Review],
    *,
    cutoff_month: str = DEMO_TODAY_YYYYMM,
) -> list[CustomerMonth]:
    """Panel data — one row per customer per month from first order
    through `cutoff_month`.

    Synthesizes:
      - `visits` per month, with churning-customer decay over the
        2-3 months before their last order
      - `purchases` + `spent_eur` from this month's actual orders
      - latest review snapshot in this month (if any)
      - `tenure_months_at_month` from first-order distance
      - `churned_in_3_months` forward-looking label

    Volumes: ~3000 customers × ~12 months avg ≈ 35-40k rows.
    """
    # Index orders by (customer_id, month) for fast per-month aggregates.
    orders_by_cm: dict[tuple[str, str], list[Order]] = {}
    first_order_month: dict[str, str] = {}
    for o in orders:
        orders_by_cm.setdefault((o.customer_id, o.month), []).append(o)
        prev = first_order_month.get(o.customer_id)
        if prev is None or o.month < prev:
            first_order_month[o.customer_id] = o.month

    # Index reviews by (customer_id, month) — keep the latest by id if
    # multiple in the same month.
    review_by_cm: dict[tuple[str, str], Review] = {}
    for r in reviews:
        key = (r.customer_id, r.created_at)
        prev_r = review_by_cm.get(key)
        if prev_r is None or r.review_id > prev_r.review_id:
            review_by_cm[key] = r

    persona_ids = {p.customer_id for p in PERSONAS}
    out: list[CustomerMonth] = []
    cm_counter = 1

    for c in customers:
        first_m = first_order_month.get(c.customer_id)
        if first_m is None:
            # No orders → no panel rows. Rare edge case (every customer
            # gets ≥ 1 order in `_orders_per_customer`).
            continue

        # Iterate from first order month through cutoff (frozen today).
        n_months = _months_between(first_m, cutoff_month) + 1
        if n_months <= 0:
            continue

        # Disposition + base visits per customer (computed once).
        is_churning_customer = c.churned
        base_visits = _BASE_VISITS_BY_SEGMENT.get(c.segment, 8)
        # Personas are bumped up a touch so their at-risk score is
        # unambiguously low — they drive the For You / Smart Search
        # demos and should never surface in the at-risk list.
        if c.customer_id in persona_ids:
            base_visits = int(base_visits * 1.3)

        for i in range(n_months):
            m = _add_months(first_m, i)
            decay = _decay_factor(is_churning_customer, m, c.last_order_month)
            # Visit count: base × decay + gaussian noise. Floor at 0.
            visits = max(0, int(base_visits * decay + rng.gauss(0, 1.5)))

            month_orders = orders_by_cm.get((c.customer_id, m), [])
            n_purchases = len(month_orders)
            spent = sum(o.total_eur for o in month_orders)

            review = review_by_cm.get((c.customer_id, m))

            # Forward label: customer is overall churned AND row's
            # month is at or after their last order. For active
            # customers (not churned), every row is False. See ADR
            # 0013 for the rationale.
            label = bool(
                c.churned
                and c.last_order_month is not None
                and m >= c.last_order_month
            )

            out.append(CustomerMonth(
                customer_month_id=f"{c.customer_id}-{m}",
                customer_id=c.customer_id,
                month=m,
                visits=visits,
                purchases=n_purchases,
                spent_eur=_round_eur(spent),
                segment=c.segment,
                pet_size=c.pet_size,
                region=c.region,
                tenure_months_at_month=i,
                latest_rating=review.rating if review is not None else None,
                latest_sentiment=review.sentiment if review is not None else None,
                latest_category=review.category if review is not None else None,
                churned_in_3_months=label,
            ))
            cm_counter += 1

    return out


# ── Operate section: monthly_sales + inventory + price_history ─────


_SEASON_BY_MONTH: dict[int, str] = {
    1: "winter", 2: "winter", 3: "spring",
    4: "spring", 5: "spring", 6: "summer",
    7: "summer", 8: "summer", 9: "autumn",
    10: "autumn", 11: "autumn", 12: "winter",
}


# Per-category lead times (days) used by Inventory. Food → faster
# turn, accessories / aquarium → longer. Tuned so the reorder
# workflow surfaces a meaningful spread of "critical" SKUs (food)
# vs "overstock" risk (aquarium accessories).
_LEAD_TIME_BY_CATEGORY: dict[str, int] = {
    "dry-food":       7,
    "wet-food":      10,
    "treats":        14,
    "dental-treats": 14,
    "litter":        10,
    "accessories":   21,
    "toys":          21,
    "grooming":      14,
    "health":        14,
    "aquarium":      28,
}


def gen_monthly_sales(
    products: list[Product],
    orders: list[Order],
    lines: list[OrderLine],
) -> list[MonthlySale]:
    """Roll `order_lines` into per-SKU per-month aggregates.

    Each emitted row is one `(sku, month)` with units_sold,
    revenue_eur, unique_customers + denormalised profile. Only
    months with at least one sale are emitted — empty months
    carry no conditioning signal for `_predict`.

    The denormalised `pet_type / category / brand / season`
    columns let Aito's `_predict units_sold` condition without
    traversing back through `products` (single-hop only).
    """
    sku_to_product = {p.sku: p for p in products}
    order_to_month = {o.order_id: o.month for o in orders}
    order_to_customer = {o.order_id: o.customer_id for o in orders}

    agg: dict[tuple[str, str], dict] = {}
    for ln in lines:
        month = order_to_month.get(ln.order_id)
        if month is None:
            continue
        key = (ln.product_sku, month)
        bucket = agg.setdefault(
            key, {"units": 0, "revenue": 0.0, "customers": set()}
        )
        bucket["units"] += ln.qty
        prod = sku_to_product.get(ln.product_sku)
        if prod is not None:
            bucket["revenue"] += prod.price_eur * ln.qty
        cust = order_to_customer.get(ln.order_id)
        if cust:
            bucket["customers"].add(cust)

    out: list[MonthlySale] = []
    for (sku, month), data in sorted(agg.items()):
        prod = sku_to_product.get(sku)
        if prod is None or data["units"] == 0:
            continue
        month_int = int(month.split("-")[1])
        out.append(MonthlySale(
            monthly_sale_id=f"{sku}-{month}",
            product_sku=sku,
            month=month,
            units_sold=int(data["units"]),
            revenue_eur=_round_eur(data["revenue"]),
            unique_customers=len(data["customers"]),
            pet_type=prod.pet_type,
            category=prod.category,
            brand=prod.brand,
            season=_SEASON_BY_MONTH[month_int],
        ))
    return out


def gen_inventory(
    rng: random.Random,
    products: list[Product],
    monthly_sales: list[MonthlySale],
) -> list[InventoryRow]:
    """Synthesise stock + lead-time + reorder thresholds per SKU.

    Engineered band distribution (drives the Inventory view's
    cash-impact narrative):

      ~10 %  critical     stock <  reorder_point
      ~25 %  low          stock <  reorder_point × 1.5
      ~50 %  ok
      ~15 %  overstock    stock >  reorder_point × 5

    Reorder point = lead-time × daily demand + safety stock.
    Daily demand is computed from the SKU's average monthly sales
    in `monthly_sales`.
    """
    sku_demand: dict[str, list[int]] = {}
    for ms in monthly_sales:
        sku_demand.setdefault(ms.product_sku, []).append(ms.units_sold)

    out: list[InventoryRow] = []
    for p in products:
        sales = sku_demand.get(p.sku, [])
        avg_monthly = (sum(sales) / len(sales)) if sales else 1
        avg_monthly = max(1, int(round(avg_monthly)))
        daily_demand = avg_monthly / 30.0
        lead_time = _LEAD_TIME_BY_CATEGORY.get(p.category, 14)
        safety_stock = max(2, int(daily_demand * 7))   # ~1 week buffer
        reorder_point = max(
            safety_stock + 1,
            int(daily_demand * lead_time) + safety_stock,
        )

        roll = rng.random()
        if roll < 0.10:
            # Critical: under reorder point
            current_stock = max(0, int(reorder_point * rng.uniform(0.05, 0.7)))
        elif roll < 0.35:
            # Low: just above reorder point (never dips below — that's
            # the critical band's job; non-overlapping ranges keep the
            # band counts predictable).
            current_stock = int(reorder_point * rng.uniform(1.05, 1.4))
        elif roll < 0.85:
            # OK: healthy band
            current_stock = int(reorder_point * rng.uniform(1.5, 3.5))
        else:
            # Overstock: tied capital warning territory
            current_stock = int(reorder_point * rng.uniform(5.0, 12.0))

        unit_cost = _round_eur(p.price_eur * 0.6)   # ≈ 60 % of retail
        supplier_idx = (int(p.sku.split("-")[-1]) % 12) + 1
        supplier = f"S-{supplier_idx:02d}"
        last_received = f"2026-{rng.choice([1, 2, 3, 4]):02d}"
        out.append(InventoryRow(
            sku=p.sku,
            current_stock=current_stock,
            unit_cost_eur=unit_cost,
            lead_time_days=lead_time,
            reorder_point=reorder_point,
            safety_stock=safety_stock,
            supplier=supplier,
            last_received_month=last_received,
        ))
    return out


def gen_price_history(
    rng: random.Random,
    products: list[Product],
    monthly_sales: list[MonthlySale],
) -> list[PriceObservation]:
    """Synthesise per-SKU per-month price snapshots.

    Most months: price ≈ list ± 5 %. ~15 % of months: promotional
    drop of 15-30 % off list. ~15 %: mild discount of 5-15 %.
    Aito's `_relate` over price-band ↔ units_sold then surfaces
    sweet-spot patterns: "category X sells 2.3× more in the
    promo band than at list price".
    """
    by_sku: dict[str, list[str]] = {}
    for ms in monthly_sales:
        by_sku.setdefault(ms.product_sku, []).append(ms.month)

    out: list[PriceObservation] = []
    for p in products:
        months = by_sku.get(p.sku, [])
        list_price = p.price_eur
        for month in months:
            roll = rng.random()
            if roll < 0.15:
                discount = rng.uniform(0.15, 0.30)     # promo
            elif roll < 0.30:
                discount = rng.uniform(0.05, 0.15)     # mild
            else:
                discount = rng.uniform(-0.05, 0.05)    # near list
            price = _round_eur(list_price * (1.0 - discount))
            out.append(PriceObservation(
                price_observation_id=f"{p.sku}-{month}",
                product_sku=p.sku,
                month=month,
                price_eur=price,
                list_price_eur=_round_eur(list_price),
                discount_pct=round(discount * 100, 1),
            ))
    return out


# ── Output ──────────────────────────────────────────────────────────

def _to_json_dict(obj) -> dict:
    """Strip None values from output. Aito treats absent and null-typed
    differently for nullable columns — we send absent for nulls."""
    raw = asdict(obj)
    return {k: v for k, v in raw.items() if v is not None}


def write_json(path: Path, items: Iterable) -> None:
    payload = [_to_json_dict(o) for o in items]
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def main() -> None:
    rng = random.Random(RNG_SEED)
    print(f"Generating PetNord fixtures (seed={RNG_SEED})...")

    products = gen_products(rng)
    customers = gen_customers(rng)
    orders, lines = gen_orders_and_lines(rng, customers, products)

    # Post-pass: derive customer-level aggregates from the order
    # history (total_orders, total_spent_eur, last_order_month,
    # churned). Powers the Churn view's `_predict` features.
    backfill_customer_aggregates(customers, orders)

    # Reviews come last — they consume a few RNG draws but no
    # earlier signal depends on them. The RNG state at this point is
    # deterministic given the seed; reviews land byte-identical
    # across runs.
    reviews = gen_reviews(rng, products, customers, orders, lines)

    # Forward-looking churn label per review, derived from each
    # customer's overall churn status + the review's month.
    backfill_review_churn_label(reviews, customers)

    # Customer-month panel — the training shape for time-series churn
    # prediction. Drives the Churn view's at-risk leaderboard + the
    # `_evaluate` accuracy band. See ADR 0013.
    customer_months = gen_customer_months(rng, customers, orders, reviews)

    # Operate-section tables: SKU × month sales aggregate (drives the
    # Demand Forecast view + feeds Inventory's daily-demand), per-SKU
    # stock snapshot (Inventory's reorder workflow), and price-history
    # observations (Price Intelligence's fair-band + sweet-spot
    # `_relate`). See ADRs 0014 / 0015 / 0016.
    monthly_sales = gen_monthly_sales(products, orders, lines)
    inventory = gen_inventory(rng, products, monthly_sales)
    price_history = gen_price_history(rng, products, monthly_sales)

    write_json(DATA_DIR / "products.json", products)
    write_json(DATA_DIR / "customers.json", customers)
    write_json(DATA_DIR / "orders.json", orders)
    write_json(DATA_DIR / "order_lines.json", lines)
    write_json(DATA_DIR / "reviews.json", reviews)
    write_json(DATA_DIR / "customer_months.json", customer_months)
    write_json(DATA_DIR / "monthly_sales.json", monthly_sales)
    write_json(DATA_DIR / "inventory.json", inventory)
    write_json(DATA_DIR / "price_history.json", price_history)

    # ── Summary print ───────────────────────────────────────────────
    print(f"  products        {len(products):>6}")
    print(f"  customers       {len(customers):>6}")
    print(f"  orders          {len(orders):>6}")
    print(f"  order_lines     {len(lines):>6}")
    print(f"  reviews         {len(reviews):>6}")
    print(f"  customer_months {len(customer_months):>6}")
    print(f"  monthly_sales   {len(monthly_sales):>6}")
    print(f"  inventory       {len(inventory):>6}")
    print(f"  price_history   {len(price_history):>6}")

    # Spot-check the engineered-signal numbers so a regen makes the
    # numbers visible in the console (the *test* is `tests/test_fixtures.py`,
    # but a printout makes "did the seed change?" diagnostics fast).
    cat_share = _large_breed_cat_share(customers, products, orders, lines)
    lift = _dog_food_dental_lift(customers, products, orders, lines)
    nulled_pct = _fillable_null_share(products) * 100
    return_pct = sum(1 for ln in lines if ln.returned) / len(lines) * 100
    churn_rate = sum(1 for c in customers if c.churned) / len(customers) * 100
    cat_share_by_assigned_to = Counter(r.assigned_to for r in reviews)

    print()
    print(f"  Signal #1 — large-breed cat share : {cat_share:.2%}    (target < 1%)")
    print(f"  Signal #2 — dog-food→dental lift  : {lift:.2f}×        (target ≥ 2.5×)")
    print(f"  Signal #4 — products w/ ≥2 nulls  : {nulled_pct:.1f}%  (target 4–6%)")
    print(f"  Signal #5 — returned share        : {return_pct:.2f}%  (target 2.5–3.5%)")
    print(f"  Signal #6 — churn rate            : {churn_rate:.1f}%  (target 25–35%)")
    print(f"  Signal #7 — reviews per agent     : "
          f"{dict(cat_share_by_assigned_to)}")

    # Panel-data sanity: forward churn label rate + last-month visit
    # decay for churning vs active customers.
    n_panel = len(customer_months)
    n_panel_pos = sum(1 for cm in customer_months if cm.churned_in_3_months)
    panel_rate = (n_panel_pos / n_panel * 100) if n_panel else 0.0
    # Visits at the most recent month per customer — comparing
    # active vs churned-customer rows.
    latest_per_cust: dict[str, CustomerMonth] = {}
    for cm in customer_months:
        prev = latest_per_cust.get(cm.customer_id)
        if prev is None or cm.month > prev.month:
            latest_per_cust[cm.customer_id] = cm
    active_visits = [
        cm.visits for cm in latest_per_cust.values()
        if not cm.churned_in_3_months
    ]
    churned_visits = [
        cm.visits for cm in latest_per_cust.values()
        if cm.churned_in_3_months
    ]
    avg_active = sum(active_visits) / len(active_visits) if active_visits else 0.0
    avg_churned = sum(churned_visits) / len(churned_visits) if churned_visits else 0.0
    # Review churn-label share — drives the Feedback view's 4th predict.
    rev_churn_share = (
        sum(1 for r in reviews if r.churn_within_90d) / len(reviews) * 100
        if reviews else 0.0
    )
    print(f"  Signal #8 — panel churn label     : {panel_rate:.1f}% of rows  "
          f"(target 18–32%)")
    print(f"  Signal #9 — latest-month visits   : "
          f"active {avg_active:.1f}  vs churned {avg_churned:.1f}  "
          f"(churned should be < 50% of active)")
    print(f"  Signal #10 — review churn share   : {rev_churn_share:.1f}%  "
          f"(target 8–18%)")

    # Operate-section signals — inventory band distribution + monthly-
    # sales coverage. Together they drive the Demand / Inventory /
    # Price views' headline numbers.
    inv_critical = sum(1 for inv in inventory if inv.current_stock < inv.reorder_point)
    inv_overstock = sum(
        1 for inv in inventory
        if inv.current_stock > inv.reorder_point * 5
    )
    inv_critical_pct = inv_critical / len(inventory) * 100 if inventory else 0
    inv_overstock_pct = inv_overstock / len(inventory) * 100 if inventory else 0
    tied_capital = sum(
        max(0, (inv.current_stock - inv.reorder_point * 2)) * inv.unit_cost_eur
        for inv in inventory
    )
    print(f"  Signal #11 — inventory critical   : {inv_critical_pct:.1f}%  "
          f"(target 8-14%)")
    print(f"  Signal #11 — inventory overstock  : {inv_overstock_pct:.1f}%  "
          f"(target 12-20%)")
    print(f"  Signal #11 — tied capital         : "
          f"€{tied_capital:,.0f}  (overstock × unit_cost)")
    ms_skus = {ms.product_sku for ms in monthly_sales}
    ms_coverage = len(ms_skus) / len(products) * 100 if products else 0
    print(f"  Signal #12 — monthly_sales SKUs   : "
          f"{len(ms_skus)}/{len(products)} ({ms_coverage:.1f}%)")

    print()
    print("  Persona top-5 (pet_type, category) pairs:")
    for persona in PERSONAS:
        pairs = _persona_top_pairs(persona.customer_id, products, orders, lines)
        formatted = ", ".join(f"({pt},{cat})" for pt, cat in pairs)
        print(f"    {persona.name_hint:6s} {persona.customer_id}  {formatted}")
    overlaps = _persona_overlap_summary(products, orders, lines)
    print()
    print("  Signal #3 — persona top-5 pair overlap:")
    for (a, b), shared in overlaps.items():
        marker = "✓" if len(shared) <= 1 else "✗"
        print(f"    {marker} {a} ∩ {b}: {len(shared)} shared  {list(shared) if shared else ''}")


# ── Signal-validation helpers (also imported by tests) ─────────────

def _dog_food_dental_lift(
    customers: list[Customer],
    products: list[Product],
    orders: list[Order],
    lines: list[OrderLine],
) -> float:
    """Lift of P(dental-treats in order | dog-food in order)
    vs P(dental-treats in any order). Only over orders from
    dog-leaning customers."""
    sku_to_product = {p.sku: p for p in products}

    lines_by_order: dict[str, list[OrderLine]] = {}
    for ln in lines:
        lines_by_order.setdefault(ln.order_id, []).append(ln)

    # Compute over ALL orders. This matches how Aito's `_relate`
    # frames the conditional: "across the whole table, given X is
    # in the row, how much more likely is Y?". Cat-owner / aquarium
    # orders contribute zero on both sides of the condition, which
    # is exactly what makes the lift high — the conditioning set is
    # narrow.
    n_orders = len(orders)
    n_orders_with_dental = 0
    n_orders_with_dryfood_dog = 0
    n_orders_with_dryfood_dog_and_dental = 0

    for o in orders:
        ols = lines_by_order.get(o.order_id, [])
        has_dental = any(
            sku_to_product[ln.product_sku].category == "dental-treats"
            for ln in ols
        )
        has_dryfood_dog = any(
            sku_to_product[ln.product_sku].category == "dry-food"
            and sku_to_product[ln.product_sku].pet_type == "dog"
            for ln in ols
        )
        if has_dental:
            n_orders_with_dental += 1
        if has_dryfood_dog:
            n_orders_with_dryfood_dog += 1
            if has_dental:
                n_orders_with_dryfood_dog_and_dental += 1

    if n_orders == 0 or n_orders_with_dryfood_dog == 0:
        return 0.0
    p_dental = n_orders_with_dental / n_orders
    p_dental_given_dryfood = n_orders_with_dryfood_dog_and_dental / n_orders_with_dryfood_dog
    if p_dental == 0:
        return 0.0
    return p_dental_given_dryfood / p_dental


def _large_breed_cat_share(
    customers: list[Customer],
    products: list[Product],
    orders: list[Order],
    lines: list[OrderLine],
) -> float:
    sku_pet = {p.sku: p.pet_type for p in products}
    order_to_customer = {o.order_id: o.customer_id for o in orders}
    target_ids = {
        c.customer_id for c in customers
        if c.segment == "dog_owner" and c.pet_size == "large"
    }
    n_total = 0
    n_cat = 0
    for ln in lines:
        cust = order_to_customer.get(ln.order_id)
        if cust not in target_ids:
            continue
        n_total += 1
        if sku_pet[ln.product_sku] == "cat":
            n_cat += 1
    return (n_cat / n_total) if n_total else 0.0


def _fillable_null_share(products: list[Product]) -> float:
    """Share of FILLABLE_CATEGORIES products with ≥ 2 of
    {weight_kg, dietary, tax_class} nulled. Drives signal #4."""
    pool = [p for p in products if p.category in FILLABLE_CATEGORIES]
    if not pool:
        return 0.0
    nulled = sum(
        1 for p in pool
        if [p.weight_kg, p.dietary, p.tax_class].count(None) >= 2
    )
    return nulled / len(pool)


def _persona_overlap_summary(
    products: list[Product],
    orders: list[Order],
    lines: list[OrderLine],
) -> dict[tuple[str, str], set[tuple[str, str]]]:
    """For each unordered pair of personas, return the intersection
    of their top-5 (pet_type, category) pairs."""
    pair_lists = {
        p.name_hint: set(_persona_top_pairs(p.customer_id, products, orders, lines))
        for p in PERSONAS
    }
    out: dict[tuple[str, str], set[tuple[str, str]]] = {}
    keys = list(pair_lists.keys())
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            out[(a, b)] = pair_lists[a] & pair_lists[b]
    return out


def _persona_top_pairs(
    persona_id: str,
    products: list[Product],
    orders: list[Order],
    lines: list[OrderLine],
) -> list[tuple[str, str]]:
    """Top 5 (pet_type, category) pairs in this persona's order
    history, ranked by line count."""
    sku_to_product = {p.sku: p for p in products}
    order_to_customer = {o.order_id: o.customer_id for o in orders}
    counts: Counter[tuple[str, str]] = Counter()
    for ln in lines:
        if order_to_customer.get(ln.order_id) != persona_id:
            continue
        p = sku_to_product[ln.product_sku]
        counts[(p.pet_type, p.category)] += 1
    return [pair for pair, _ in counts.most_common(5)]


if __name__ == "__main__":
    main()
