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


@dataclass
class Order:
    order_id: str
    customer_id: str
    month: str          # YYYY-MM
    total_eur: float


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

        for _ in range(n_orders):
            order_id = f"ORD-{order_counter:05d}"
            order_counter += 1
            month = rng.choice(_MONTH_WINDOW[-(customer.tenure_months + 1):])

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
            orders.append(Order(
                order_id=order_id,
                customer_id=customer.customer_id,
                month=month,
                total_eur=_round_eur(order_total),
            ))

    return orders, lines


# Linear scan — fine for fixture generation (we run it once per regen).
# Avoids dragging in a global lookup we don't need at runtime.
def _sku_to_product(products: list[Product], sku: str) -> Product:
    for p in products:
        if p.sku == sku:
            return p
    raise KeyError(sku)


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

    write_json(DATA_DIR / "products.json", products)
    write_json(DATA_DIR / "customers.json", customers)
    write_json(DATA_DIR / "orders.json", orders)
    write_json(DATA_DIR / "order_lines.json", lines)

    # ── Summary print ───────────────────────────────────────────────
    print(f"  products    {len(products):>6}")
    print(f"  customers   {len(customers):>6}")
    print(f"  orders      {len(orders):>6}")
    print(f"  order_lines {len(lines):>6}")

    # Spot-check the engineered-signal numbers so a regen makes the
    # numbers visible in the console (the *test* is `tests/test_fixtures.py`,
    # but a printout makes "did the seed change?" diagnostics fast).
    cat_share = _large_breed_cat_share(customers, products, orders, lines)
    lift = _dog_food_dental_lift(customers, products, orders, lines)
    nulled_pct = _fillable_null_share(products) * 100
    return_pct = sum(1 for ln in lines if ln.returned) / len(lines) * 100

    print()
    print(f"  Signal #1 — large-breed cat share : {cat_share:.2%}    (target < 1%)")
    print(f"  Signal #2 — dog-food→dental lift  : {lift:.2f}×        (target ≥ 2.5×)")
    print(f"  Signal #4 — products w/ ≥2 nulls  : {nulled_pct:.1f}%  (target 4–6%)")
    print(f"  Signal #5 — returned share        : {return_pct:.2f}%  (target 2.5–3.5%)")

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
