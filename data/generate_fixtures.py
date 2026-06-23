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
import math
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


# ── Segment-level affinity (within-pet_type signal) ───────────────
#
# These tables drive `_apply_segment_affinity` (see below). They
# inject within-pet_type, between-segment differentiation in brand
# and dietary so `_recommend` over `goal: customer_segment` with
# `basedOn: [brand, dietary, pet_type]` actually has signal to rank
# on. Without this, pet_type is already implied by the where clause
# (customer_pet_size correlates ~98 % with pet_type), and brand is
# largely pet_type-determined (Whiskas = cat, JBL = aquarium etc.),
# so `basedOn` rounds to no-op. Cf. `docs/aito-cheatsheet.md`
# §"Does `basedOn: []` cost accuracy?".
#
# Affinity is applied via a per-customer-per-line sub-RNG, so the
# existing demo signals (large-breed cat share, dog-food→dental
# lift, persona top-5 overlaps) stay byte-identical.

# Each segment's "preferred" brands inside its dominant pet_type.
# Picked from the BRAND_CATEGORIES table above so we don't bias
# toward brands that don't sell in those segments anyway.
BRAND_AFFINITY_BY_SEGMENT: dict[str, set[str]] = {
    "dog_owner":   {"Royal Canin", "Hill's Science Plan", "Acana", "Orijen"},
    "multi_pet":   {"PetNord", "Eukanuba", "Whimzees", "Kong", "Trixie"},
    "cat_owner":   {"Royal Canin", "Hill's Science Plan", "Acana", "Sheba"},
    # aquarium_owner / small_animal_owner already concentrate on a
    # small brand set (JBL/Tetra, Trixie/Beaphar respectively); no
    # additional affinity needed.
}

# Dietary tags each segment over-indexes on. Subset of DIETARIES.
DIETARY_AFFINITY_BY_SEGMENT: dict[str, set[str]] = {
    "dog_owner":   {"large-breed", "grain-free"},
    "multi_pet":   {"sensitive", "senior"},
    "cat_owner":   {"indoor", "weight-control"},
}

# Probability that a given line gets substituted with an affinity-
# aligned product from the same (pet_type, category) slice. Tuned
# to lift segment ↔ brand and segment ↔ dietary correlations into
# `_recommend basedOn` territory without distorting category
# distributions (substitution stays in the same category).
SEGMENT_AFFINITY_SUB_RATE: float = 0.50


# ── Brand tier ────────────────────────────────────────────────────
#
# Drives the lifestyle ↔ brand correlation. Premium customers
# over-index on premium brands (~70 % of brand picks); budget
# customers on mass brands (~70 %). Brands not in either tier are
# tier-neutral (Sheba, Felix, Whimzees) and contribute mid.
PREMIUM_BRANDS: set[str] = {
    "Royal Canin", "Hill's Science Plan", "Acana", "Orijen",
}
MASS_BRANDS: set[str] = {
    "PetNord", "Eukanuba", "Whiskas", "Kong", "Trixie",
    "JBL", "Tetra", "Beaphar",
}


# ── Tag taxonomy ──────────────────────────────────────────────────
#
# Products get 4-8 tags synthesised from brand-tier + dietary +
# category. Tags add a dense, segment-correlated feature for Aito's
# `_recommend basedOn`. Crucially they're DIFFERENT axes than the
# existing categorical columns — `category` says "what kind of
# item", tags say "what lifestyle / use-case / consumer signal".

# Category → list of lifestyle markers. Each product picks a
# deterministic subset based on its name + price.
CATEGORY_TAGS: dict[str, list[str]] = {
    "dry-food":      ["complete", "kibble"],
    "wet-food":      ["complete", "pouch"],
    "treats":        ["indulgent", "training"],
    "dental-treats": ["dental", "training", "preventive"],
    "toys":          ["interactive", "chew"],
    "accessories":   ["everyday", "outdoor"],
    "litter":        ["clumping", "absorbent"],
    "health":        ["supplement", "preventive"],
    "grooming":      ["spa", "everyday"],
    "aquarium":      ["tank", "filter"],
}

# Dietary tag → lifestyle marker. Most map 1:1 but the wording
# leans toward consumer-facing copy.
DIETARY_TAG: dict[str, str] = {
    "grain-free":      "natural",
    "senior":          "senior-care",
    "puppy":           "puppy-stage",
    "large-breed":     "large-breed",
    "sensitive":       "hypoallergenic",
    "indoor":          "indoor-cat",
    "weight-control":  "diet",
}


# ── Customer profile distributions ─────────────────────────────────
#
# Each customer is sampled at creation with these latent traits.
# Marginal distributions are deliberately balanced (25 / 50 / 25)
# so each archetype lands on hundreds of customers and analytics
# views surface clean within-segment patterns. See ADR 0017.

LIFESTYLE_WEIGHTS:       tuple[float, float, float] = (0.25, 0.50, 0.25)
HEALTH_FOCUS_WEIGHTS:    tuple[float, float, float] = (0.25, 0.50, 0.25)
TREAT_AFFINITY_WEIGHTS:  tuple[float, float, float] = (0.25, 0.50, 0.25)
BRAND_LOYALTY_WEIGHTS:   tuple[float, float]         = (0.30, 0.70)

# Per-segment override of lifestyle base rates — segment ↔ lifestyle
# is engineered to be partially correlated so analytics can surface
# "aquarium owners skew premium" / "small-animal owners skew budget"
# style insights without being deterministic.
LIFESTYLE_BIAS_BY_SEGMENT: dict[str, tuple[float, float, float]] = {
    "dog_owner":          (0.30, 0.50, 0.20),  # premium-leaning
    "cat_owner":          (0.30, 0.50, 0.20),  # premium-leaning
    "multi_pet":          (0.15, 0.55, 0.30),  # budget-leaning (bigger basket needs)
    "aquarium_owner":     (0.35, 0.50, 0.15),  # hobbyist premium
    "small_animal_owner": (0.10, 0.45, 0.45),  # budget-skew (kids' pets)
}


# ── Finnish name pool ─────────────────────────────────────────────
#
# Hand-curated so the demo's customer list reads like a real Finnish
# pet-shop database (PetNord is Finnish-positioned per ADR 0001).
# Roughly 60 first names × 50 last names ⇒ 3000 unique combos for
# our 2997 generic customers without collisions. Personas keep their
# hand-curated names: Maija Lehtonen / Olli Mäkelä / Saara Virtanen.

FINNISH_FIRST_NAMES: list[str] = [
    # Female
    "Aino", "Anna", "Anneli", "Eeva", "Elina", "Emilia", "Hanna",
    "Helena", "Helmi", "Iida", "Inkeri", "Jenni", "Kaisa", "Katja",
    "Kirsti", "Laura", "Leena", "Liisa", "Lotta", "Marja", "Mervi",
    "Minna", "Nelli", "Niina", "Pirkko", "Päivi", "Raija", "Riitta",
    "Sanna", "Satu", "Sirpa", "Sofia", "Suvi", "Taina", "Tiina",
    "Tuula", "Ulla", "Venla", "Virpi",
    # Male
    "Aleksi", "Antero", "Antti", "Eemil", "Eero", "Esa", "Hannu",
    "Heikki", "Ilkka", "Ismo", "Jaakko", "Janne", "Jari", "Jouko",
    "Juha", "Juhani", "Jukka", "Kalle", "Kari", "Lauri", "Markku",
    "Matti", "Mika", "Niko", "Onni", "Pasi", "Pekka", "Petri",
    "Sami", "Seppo", "Tapio", "Teemu", "Timo", "Toivo", "Tuomas",
    "Vesa", "Väinö",
]

FINNISH_LAST_NAMES: list[str] = [
    "Korhonen", "Virtanen", "Mäkinen", "Nieminen", "Mäkelä",
    "Hämäläinen", "Laine", "Heikkinen", "Koskinen", "Järvinen",
    "Lehtonen", "Lehtinen", "Saarinen", "Salminen", "Heinonen",
    "Niemi", "Heikkilä", "Kinnunen", "Salonen", "Turunen",
    "Salo", "Laitinen", "Tuominen", "Rantanen", "Karjalainen",
    "Jokinen", "Mattila", "Savolainen", "Lahtinen", "Ahonen",
    "Ojala", "Leppänen", "Kallio", "Hiltunen", "Anttila",
    "Pitkänen", "Manninen", "Koivisto", "Hakala", "Aaltonen",
    "Niemelä", "Kauppinen", "Toivonen", "Lampinen", "Sinkkonen",
    "Mikkonen", "Kuusisto", "Rinne", "Vuori", "Nurmi",
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
    name: str            # full display name — surfaced in UI
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
    # Hand-curated latent traits — match the persona's narrative.
    # Maija: cat owner, premium, health-conscious, low treat, loyal.
    # Olli: multi-pet, mid lifestyle, low health focus, treat-loving,
    # flexible (tries new brands). Saara: large-dog owner, premium,
    # health-conscious, mid treats, loyal.
    lifestyle: str = "mid"
    health_focus: str = "medium"
    treat_affinity: str = "medium"
    brand_loyalty: str = "flexible"


PERSONAS: list[Persona] = [
    Persona("CUST-00001", "Maija Lehtonen",  "cat_owner",
            None,    "helsinki", tenure_months=18, target_orders=12,
            lifestyle="premium", health_focus="high",
            treat_affinity="low", brand_loyalty="loyal"),
    Persona("CUST-00002", "Olli Mäkelä",     "multi_pet",
            "small", "tampere",  tenure_months=9,  target_orders=10,
            # Heavily dog-leaning multi_pet. Keeps Maija ∩ Olli top-5
            # ≤ 1 shared pair while preserving the multi_pet flavour
            # (Olli still buys cat products occasionally).
            pet_type_weights={"dog": 0.85, "cat": 0.15},
            lifestyle="mid", health_focus="low",
            treat_affinity="high", brand_loyalty="flexible"),
    Persona("CUST-00003", "Saara Virtanen",  "dog_owner",
            "large", "espoo",    tenure_months=26, target_orders=14,
            lifestyle="premium", health_focus="high",
            treat_affinity="medium", brand_loyalty="loyal"),
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
    # Space-separated lifestyle markers synthesised from existing
    # attributes: brand-tier ("premium"/"mass"), dietary translated to
    # tag form (grain-free → "natural", senior → "senior-care", etc.),
    # and category-specific markers ("complete"/"indulgent"/"dental"/
    # "interactive"/...). Stored as a Text column so Aito's `_predict`
    # and `_recommend basedOn: ["tags"]` can use token-level priors,
    # and so `_search where {tags: {$match: "premium"}}` works without
    # extra schema. See ADR 0017.
    tags: str = ""


@dataclass
class Customer:
    customer_id: str
    # Display name — "Aino Korhonen". Deterministic per customer_id
    # so the UI can pretend this is a real Finnish pet store. Personas
    # keep their hand-curated names (Maija Lehtonen / Olli Mäkelä /
    # Saara Virtanen) to preserve the demo script. See ADR 0017.
    name: str
    segment: str
    pet_size: str | None
    region: str
    tenure_months: int
    # ── Latent profile traits, sampled at creation with per-segment
    # base rates and per-customer noise. Stable across the customer's
    # purchase history. Drive product-level preferences via
    # `_customer_product_score` (brand tier, dietary affinity, brand
    # loyalty) and category-level via `_category_bias_for_customer`
    # (treat affinity). Denormalised onto `order_lines` so Aito can
    # condition `_recommend` / `_predict` on them in one hop. See
    # ADR 0017.
    lifestyle: str = "mid"            # premium | mid | budget
    health_focus: str = "medium"      # high | medium | low
    treat_affinity: str = "medium"    # high | medium | low
    brand_loyalty: str = "flexible"   # loyal | flexible
    # 1-3 brands this customer over-indexes on (relevant when
    # brand_loyalty == "loyal"). Excluded from JSON output but kept
    # in-memory during generation so the order loop can use them.
    favorite_brands: tuple[str, ...] = ()
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
    customer_name: str              # denormalised — drives Churn UI labels
    month: str                      # YYYY-MM
    visits: int                     # synthetic per-month site visits
    purchases: int                  # orders this month
    spent_eur: float                # sum of order totals this month
    segment: str                    # denormalised
    pet_size: str | None            # denormalised, nullable
    region: str                     # denormalised
    # Latent profile traits — give the Churn view's `_predict
    # churned_in_3_months` access to lifestyle / health / treat /
    # loyalty as features. Engineered correlation with churn
    # (budget+flexible customers churn at higher rate) gives the
    # model real signal to weight. See ADR 0017.
    lifestyle: str                  # premium | mid | budget
    health_focus: str               # high | medium | low
    treat_affinity: str             # high | medium | low
    brand_loyalty: str              # loyal | flexible
    tenure_months_at_month: int     # months since first order at this row's month
    latest_rating: int | None       # most-recent review rating in this month
    latest_sentiment: str | None    # sentiment of that review
    latest_category: str | None     # category of that review
    churned_in_3_months: bool       # the forward target


@dataclass
class MonthlySale:
    """Per-SKU per-month sales aggregate. Powers the Demand
    Forecast view's `_estimate units_sold` and the Inventory view's
    days-of-supply arithmetic. Denormalised pet_type + category +
    brand + season + price_eur so Aito conditions in one hop
    without traversal back to products. See ADR 0014.

    `price_eur` is the actual realised price for this SKU in this
    month (revenue / units). Powers the Price view's interactive
    demand curve — Aito's `_estimate units_sold` with `price_eur`
    in the where lets us walk the curve at +/-15 % shifts.
    """
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
    price_eur: float           # realised price (revenue / units) — drives demand-curve _estimate


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
class WinbackCampaign:
    """Historical email re-engagement campaign — sent to a customer
    who had been inactive for `recency_bucket` days at send time.
    The `responded` outcome label is what Aito learns from to predict
    response rates for currently-churned customers. See ADR 0020.
    """
    campaign_id: str               # "WB-NNNNN"
    customer_id: str               # link → customers.customer_id
    product_sku: str               # link → products.sku (the SKU emailed)
    sent_month: str                # YYYY-MM
    # Days since the customer's last order at send time, bucketed
    # for Aito's K-NN to read cleanly. Strong predictor of response.
    recency_bucket: str            # "0-90d" | "90-180d" | "180d+"
    # Denormalised customer profile so Aito conditions in one hop.
    customer_segment: str
    customer_pet_size: str | None  # nullable
    customer_lifestyle: str
    customer_health_focus: str
    # Denormalised product attributes for the same reason.
    product_pet_type: str
    product_category: str
    product_brand: str
    # Outcome label — what Aito's `_predict responded` learns.
    responded: bool
    # Order value if the customer responded (0 if not). Powers the
    # revenue-impact roll-up in the Win-back view.
    order_value_eur: float


@dataclass
class Impression:
    """One product shown to a customer in a browsing context, with the
    funnel outcome recorded. A *view* is implicit (every row is a view);
    the three booleans capture the funnel beyond it. This is the table
    that gives recommendations a real conversion KPI to rank on —
    `_recommend product_sku goal: {purchased: true}`. See ADR 0021.

    Funnel monotonicity invariant: purchased ⇒ added_to_cart ⇒ clicked.
    Enforced at generation; asserted by `./do aito-check`.
    """
    impression_id: str             # "IMP-NNNNNNN"
    session_id: str                # groups impressions shown together
    customer_id: str               # link → customers.customer_id
    product_sku: str               # link → products.sku
    # Where the product was shown. Lets a query scope to one surface
    # (e.g. only search impressions for the Smart Search re-rank).
    surface: str                   # search | for_you | category | bought_together
    month: str                     # YYYY-MM (categorical, like orders.month)
    position: int                  # 0-based rank in the shown list (descriptive
                                   # only — never fed to recommend basedOn, ADR 0021)
    # The query string for surface == "search"; None (absent) otherwise.
    # Text so `where {search_query: {$match: "food"}}` token-matches.
    search_query: str | None = None
    # Denormalised customer profile — single-hop conditioning, same
    # rationale as order_lines (ADR 0006/0017).
    customer_segment: str = "dog_owner"
    customer_pet_size: str | None = None
    customer_lifestyle: str = "mid"
    customer_health_focus: str = "medium"
    customer_treat_affinity: str = "medium"
    customer_brand_loyalty: str = "flexible"
    # Denormalised product attributes for `basedOn` priors.
    product_pet_type: str = "dog"
    product_category: str = "dry-food"
    product_brand: str = "PetNord"
    # Funnel outcome labels — what Aito's _recommend / _predict learn.
    clicked: bool = False
    added_to_cart: bool = False
    purchased: bool = False


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
    # Latent customer-profile traits, denormalised for the same
    # single-hop reason as `customer_segment` / `customer_pet_size`.
    # Power Aito's `_recommend basedOn` and Pattern Explorer / Bought
    # Together / Purchase Analytics within-segment patterns. See
    # ADR 0017.
    customer_lifestyle: str = "mid"
    customer_health_focus: str = "medium"
    customer_treat_affinity: str = "medium"
    customer_brand_loyalty: str = "flexible"


# ── Generation ──────────────────────────────────────────────────────

def _round_eur(x: float) -> float:
    """Two-decimal rounding so JSON output is stable across runs."""
    return round(x, 2)


def _clip(x: float, lo: float, hi: float) -> float:
    """Clamp x to [lo, hi]."""
    return max(lo, min(hi, x))


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
                        tags=_synthesize_tags(brand, category, dietary, price),
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


def _name_deck(rng: random.Random, exclude: set[str]) -> list[str]:
    """Pre-shuffled deck of full Finnish names, with `exclude` (the
    persona-reserved names) removed. ~76 first × 50 last = 3800
    combinations — enough headroom for our 2997 generic customers
    without collisions or fallback gymnastics."""
    deck = [
        f"{first} {last}"
        for first in FINNISH_FIRST_NAMES
        for last in FINNISH_LAST_NAMES
        if f"{first} {last}" not in exclude
    ]
    rng.shuffle(deck)
    return deck


def _sample_customer_traits(
    rng: random.Random,
    segment: str,
) -> tuple[str, str, str, str]:
    """Sample (lifestyle, health_focus, treat_affinity, brand_loyalty)
    for a generic (non-persona) customer.

    `lifestyle` uses a per-segment bias (aquarium hobbyists skew
    premium, small-animal owners skew budget) — see
    `LIFESTYLE_BIAS_BY_SEGMENT`. The other three traits use marginal
    distributions: 25/50/25 for ternary, 30/70 for binary. Distinct
    sub-RNG draws keep traits independent so the joint space (3 × 3 ×
    3 × 2 = 54 archetypes) is broadly populated.
    """
    lifestyle_weights = LIFESTYLE_BIAS_BY_SEGMENT.get(segment, LIFESTYLE_WEIGHTS)
    lifestyle = rng.choices(("premium", "mid", "budget"), weights=lifestyle_weights)[0]
    health_focus = rng.choices(("high", "medium", "low"), weights=HEALTH_FOCUS_WEIGHTS)[0]
    treat_affinity = rng.choices(("high", "medium", "low"), weights=TREAT_AFFINITY_WEIGHTS)[0]
    brand_loyalty = rng.choices(("loyal", "flexible"), weights=BRAND_LOYALTY_WEIGHTS)[0]
    return lifestyle, health_focus, treat_affinity, brand_loyalty


def _pick_favorite_brands(
    rng: random.Random,
    segment: str,
    lifestyle: str,
    brand_loyalty: str,
) -> tuple[str, ...]:
    """For loyal customers, pick 1-2 brands they over-index on.
    Constrained to brands compatible with the segment's dominant
    pet_type AND consistent with their lifestyle tier (premium
    customers loyal to premium brands, etc.). Returns empty tuple
    for flexible customers.
    """
    if brand_loyalty != "loyal":
        return ()
    # Which brands are realistic for this segment?
    segment_to_pet = {
        "dog_owner":          "dog",
        "multi_pet":          "dog",
        "cat_owner":          "cat",
        "aquarium_owner":     "aquarium",
        "small_animal_owner": "small_animal",
    }
    pet = segment_to_pet.get(segment, "dog")
    eligible = [
        b for b, pet_cats in BRAND_CATEGORIES.items()
        if pet in pet_cats
    ]
    if lifestyle == "premium":
        pool = [b for b in eligible if b in PREMIUM_BRANDS] or eligible
    elif lifestyle == "budget":
        pool = [b for b in eligible if b in MASS_BRANDS] or eligible
    else:
        pool = eligible
    if not pool:
        return ()
    k = min(2, len(pool))
    return tuple(rng.sample(pool, k=k))


def gen_customers(rng: random.Random) -> list[Customer]:
    """Generate ~3000 customers. The three named personas (Maija /
    Olli / Saara) get fixed ids `CUST-00001..3` so the For You
    customer-switcher in the UI hits stable rows.

    Each customer gets a Finnish display name (unique within the
    dataset) and four latent profile traits sampled at creation —
    `lifestyle` / `health_focus` / `treat_affinity` / `brand_loyalty`.
    These are stable across the customer's entire purchase history,
    so a customer's tag pattern becomes inferable from a handful of
    orders. See ADR 0017.

    Name + trait + favorite-brand draws use a SEPARATE RNG instance
    seeded deterministically from the main seed. That way the main
    fixture RNG sequence is unchanged — existing demo signals (large-
    breed cat share, dog-food → dental lift, persona top-5 overlaps,
    persona last_order_month → churn cutoff) stay byte-identical.
    """
    customers: list[Customer] = []
    # Dedicated RNG for the new profile / name draws so the main
    # `rng` state is untouched after gen_customers. Seeded from
    # RNG_SEED so re-runs reproduce the same names + traits.
    profile_rng = random.Random(RNG_SEED + 17)
    # Reserve persona names from the deck.
    persona_names = {p.name for p in PERSONAS}
    name_deck = _name_deck(profile_rng, persona_names)

    for p in PERSONAS:
        favorites = _pick_favorite_brands(
            profile_rng, p.segment, p.lifestyle, p.brand_loyalty,
        )
        customers.append(Customer(
            customer_id=p.customer_id,
            name=p.name,
            segment=p.segment,
            pet_size=p.pet_size,
            region=p.region,
            tenure_months=p.tenure_months,
            lifestyle=p.lifestyle,
            health_focus=p.health_focus,
            treat_affinity=p.treat_affinity,
            brand_loyalty=p.brand_loyalty,
            favorite_brands=favorites,
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
        # The next draws (name pop, 4 trait samples, favorites) come
        # from the dedicated `profile_rng` so they don't perturb the
        # main `rng` state. Name comes from the pre-shuffled deck.
        name = name_deck.pop()
        lifestyle, health_focus, treat_affinity, brand_loyalty = _sample_customer_traits(profile_rng, segment)
        favorites = _pick_favorite_brands(profile_rng, segment, lifestyle, brand_loyalty)
        customers.append(Customer(
            customer_id=cid,
            name=name,
            segment=segment,
            pet_size=pet_size,
            region=region,
            tenure_months=tenure,
            lifestyle=lifestyle,
            health_focus=health_focus,
            treat_affinity=treat_affinity,
            brand_loyalty=brand_loyalty,
            favorite_brands=favorites,
        ))

    return customers


def _synthesize_tags(
    brand: str,
    category: str,
    dietary: str | None,
    price_eur: float,
) -> str:
    """Build a product's space-separated tag string.

    Tags come from three axes orthogonal to the existing categorical
    columns:

      - Brand-tier marker: `"premium"` or `"mass"` (or neither for
        tier-neutral brands like Sheba / Felix / Whimzees).
      - Dietary translated to consumer-facing wording via
        `DIETARY_TAG` (grain-free → `"natural"`, senior →
        `"senior-care"`, ...). Skipped when `dietary is None`.
      - Category lifestyle markers via `CATEGORY_TAGS`
        (dry-food → `"complete kibble"`, dental-treats →
        `"dental training preventive"`, ...).

    Price >= 30 EUR also adds the `"value-bundle"` tag for the
    "bulk-size" lifestyle marker — picked up by Pattern Explorer
    and the basedOn priors for budget customers.
    """
    parts: list[str] = []
    if brand in PREMIUM_BRANDS:
        parts.append("premium")
    elif brand in MASS_BRANDS:
        parts.append("mass")
    if dietary and dietary in DIETARY_TAG:
        parts.append(DIETARY_TAG[dietary])
    parts.extend(CATEGORY_TAGS.get(category, []))
    if price_eur >= 30:
        parts.append("value-bundle")
    return " ".join(parts)


# Health-focus drives preference for "wellness" dietary tags
# specifically — the food catalog is ~95 % dietary-tagged overall, so
# "any dietary" can't differentiate. Pointing high-health customers
# at the wellness sub-set (and low-health at lifestage tags + no-tag)
# creates a measurable within-pet_type signal.
WELLNESS_DIETARIES: set[str] = {"grain-free", "sensitive", "senior", "weight-control"}
LIFESTAGE_DIETARIES: set[str] = {"puppy", "large-breed", "indoor"}


def _customer_product_score(
    product: Product,
    customer: Customer,
) -> float:
    """Multiplier applied to a product's base pick weight when this
    customer is the buyer. Returns 1.0 when no trait modifies the
    product's odds — i.e. mid lifestyle, medium health, flexible
    loyalty, customer's favorite brands don't apply.

    The same `_pick_product` infrastructure runs first (pet_type
    filter + segment-level category bias); this score layers on
    top to inject within-segment customer preference. Keeps the
    existing engineered signals intact while making per-customer
    tag patterns inferable from 3-4 purchases.
    """
    score = 1.0

    # Lifestyle ↔ brand tier
    if customer.lifestyle == "premium":
        if product.brand in PREMIUM_BRANDS:
            score *= 2.6
        elif product.brand in MASS_BRANDS:
            score *= 0.55
    elif customer.lifestyle == "budget":
        if product.brand in MASS_BRANDS:
            score *= 2.2
        elif product.brand in PREMIUM_BRANDS:
            score *= 0.50

    # Health focus ↔ specific dietary tag families. Pointing at
    # value-sets rather than "any dietary" lets the signal survive
    # in a catalog that's already ~95 % dietary-tagged on food.
    if customer.health_focus == "high":
        if product.dietary in WELLNESS_DIETARIES:
            score *= 2.4
        elif product.dietary in LIFESTAGE_DIETARIES:
            score *= 0.65
    elif customer.health_focus == "low":
        if product.dietary in WELLNESS_DIETARIES:
            score *= 0.55
        elif product.dietary in LIFESTAGE_DIETARIES:
            score *= 1.3

    # Brand loyalty ↔ favorite brands. Stronger boost than the
    # other traits because the demo's "loyal customer" story needs
    # a visibly concentrated brand mix in their purchase history.
    if customer.brand_loyalty == "loyal" and product.brand in customer.favorite_brands:
        score *= 6.0

    return score


def _category_bias_for_customer(
    base_bias: dict[str, float] | None,
    customer: Customer,
) -> dict[str, float] | None:
    """Layer customer treat_affinity onto the segment-level category
    bias. High-treat customers see ~3× weight on (dental-)treats;
    low-treat customers see ~0.4× weight. Mid customers unchanged.

    Returning None when base_bias is None preserves the uniform-pick
    fallback path in `_pick_product`.
    """
    if base_bias is None:
        return None
    bias = dict(base_bias)
    if customer.treat_affinity == "high":
        for cat in ("treats", "dental-treats"):
            bias[cat] = bias.get(cat, 0.05) * 2.7
    elif customer.treat_affinity == "low":
        for cat in ("treats", "dental-treats"):
            bias[cat] = bias.get(cat, 0.05) * 0.40
    return bias


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


def _customer_preference_substitute(
    chosen: Product,
    products_by_pet_cat: dict[tuple[str, str], list[Product]],
    customer: Customer,
    persona_ids: set[str],
    line_counter: int,
) -> Product:
    """Maybe swap `chosen` for a same-(pet_type, category) product
    whose brand / dietary / tier matches the customer's *personal*
    trait profile (lifestyle, health_focus, brand_loyalty + favorite
    brands).

    Uses a sub-RNG seeded from `(customer_id, line_counter)` so the
    main fixture RNG sequence is unchanged — engineered signals from
    `_pick_product` (pet_type weights, category bias, persona overlaps,
    dog-food → dental lift) stay byte-identical. Persona customers
    are skipped entirely; their orders are hand-curated.

    The substitution is what makes Aito's `_recommend` see customer-
    level preference patterns from just 3-4 purchases — premium
    customers' baskets are dominated by premium brands across all
    their orders, health-focused customers' baskets carry dietary
    tags consistently, loyal customers concentrate on their 1-2
    favorite brands. Different from earlier `_apply_segment_affinity`
    which used segment-level preferences only — segment is already
    captured by where + goal in smart-search, so customer-level
    preference is what priors actually need to add value.
    """
    if customer.customer_id in persona_ids:
        return chosen

    seed = sum(ord(c) for c in customer.customer_id) * 1009 + line_counter
    sub_rng = random.Random(seed)

    same_slice = products_by_pet_cat.get((chosen.pet_type, chosen.category), [])
    if not same_slice:
        return chosen

    # Loyal customers' favorite brands: if one of the customer's
    # favorites is available in the same (pet_type, category) slice,
    # snap to a favorite-branded product 85 % of the time. This is
    # what gives the brand_loyalty trait its visible signal (top-2
    # brand share gap between loyal and flexible customers).
    if customer.brand_loyalty == "loyal" and customer.favorite_brands:
        favorite_in_slice = [p for p in same_slice if p.brand in customer.favorite_brands]
        if favorite_in_slice and sub_rng.random() < 0.85:
            return sub_rng.choice(favorite_in_slice)

    # General customer-preference substitution. Higher base rate
    # than the prior segment-level affinity (0.50) — customer-level
    # traits are stable across the customer's entire purchase
    # history, so the substitution should be the dominant signal.
    if sub_rng.random() > 0.65:
        return chosen

    # Weight every same-slice candidate by the customer's score; pick
    # via cumulative weighted choice. Empty / all-zero weights ⇒
    # keep the original.
    weights = [max(_customer_product_score(p, customer), 0.01) for p in same_slice]
    total = sum(weights)
    if total <= 0:
        return chosen
    return sub_rng.choices(same_slice, weights=weights, k=1)[0]


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
    # Latent profile contributes too — engineered so that Pattern
    # Explorer / Churn _relate surface lifestyle and brand_loyalty
    # as meaningful drivers. Budget customers are price-sensitive
    # and churn more readily; loyal customers stick around. See
    # ADR 0017 §"Engineered cross-trait correlations".
    if customer.lifestyle == "budget":             p += 0.08
    if customer.lifestyle == "premium":            p -= 0.04
    if customer.brand_loyalty == "flexible":       p += 0.04
    if customer.brand_loyalty == "loyal":          p -= 0.04
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

    # (pet_type, category) → products. Lookup for the segment-affinity
    # substitution that runs after `_pick_product`. Built once.
    products_by_pet_cat: dict[tuple[str, str], list[Product]] = {}
    for p in products:
        products_by_pet_cat.setdefault((p.pet_type, p.category), []).append(p)

    # Persona orders first so they get the lowest ids (CUST-00001's
    # orders are ORD-00001..). Nice for debugging in the JSON.
    persona_ids = {p.customer_id: p for p in PERSONAS}
    persona_id_set = set(persona_ids)

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
        # Layer treat_affinity onto cat_bias for generic customers only.
        # Personas keep their segment-level cat_bias untouched so their
        # hand-curated top-5 (pet_type, category) overlap signal stays
        # byte-identical.
        if persona is None:
            cat_bias = _category_bias_for_customer(cat_bias, customer)

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
                # Customer-preference substitution within (pet_type,
                # category) using a sub-RNG keyed on
                # (customer_id, line_counter). Main RNG state is
                # untouched so existing engineered signals — large-
                # breed cat share, persona top-5 overlaps, dog-food →
                # dental lift, returned share — stay byte-identical
                # for personas (skipped entirely) and identical-in-
                # distribution for the generic crowd.
                product = _customer_preference_substitute(
                    product, products_by_pet_cat, customer,
                    persona_id_set, line_counter,
                )
                if product.sku in order_skus:
                    continue
                order_skus.add(product.sku)
                qty = rng.choices([1, 2, 3], weights=[0.78, 0.18, 0.04])[0]
                # Returned rate modulated by lifestyle — budget customers
                # return more (price-sensitive, less satisfied), premium
                # return less. Overall share stays in the 2.5-3.5 % band
                # that signal-test #5 asserts.
                returned_rate = {"premium": 0.018, "mid": 0.030, "budget": 0.042}[customer.lifestyle]
                returned = rng.random() < returned_rate
                line = OrderLine(
                    line_id=f"LN-{line_counter:06d}",
                    order_id=order_id,
                    product_sku=product.sku,
                    qty=qty,
                    returned=returned,
                    customer_segment=customer.segment,
                    customer_pet_size=customer.pet_size,
                    customer_lifestyle=customer.lifestyle,
                    customer_health_focus=customer.health_focus,
                    customer_treat_affinity=customer.treat_affinity,
                    customer_brand_loyalty=customer.brand_loyalty,
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
                            customer_lifestyle=customer.lifestyle,
                            customer_health_focus=customer.health_focus,
                            customer_treat_affinity=customer.treat_affinity,
                            customer_brand_loyalty=customer.brand_loyalty,
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

# Category share is conditioned on **customer.churned** so the
# rating column becomes a meaningful predictor of churn:
# unhappy/churning customers cluster in shipping/quality/fit
# (low ratings); active customers cluster in praise (high
# ratings). The weighted average across the customer population
# preserves the original net share (~40 % praise / 22 % quality /
# 18 % shipping / 10 % fit / 10 % question).
_REVIEW_CATEGORY_WEIGHTS_ACTIVE: dict[str, float] = {
    "praise":   0.55,
    "quality":  0.16,
    "shipping": 0.12,
    "fit":      0.07,
    "question": 0.10,
}
_REVIEW_CATEGORY_WEIGHTS_CHURNED: dict[str, float] = {
    "praise":   0.12,
    "quality":  0.34,
    "shipping": 0.28,
    "fit":      0.16,
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
    # Customer churn lookup — drives the conditional category weights
    # so 1-star reviews preferentially come from churning customers.
    customer_churned: dict[str, bool] = {c.customer_id: c.churned for c in customers}

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
        # Pick category weights conditional on this customer's overall
        # churn status. Churning customers' reviews skew toward
        # complaint categories (low ratings); active customers' skew
        # toward praise. Aito then learns "rating=1 ⇒ elevated
        # P(churn)" from the conditional rate gap.
        cat_weights = (
            _REVIEW_CATEGORY_WEIGHTS_CHURNED
            if customer_churned.get(cust, False)
            else _REVIEW_CATEGORY_WEIGHTS_ACTIVE
        )
        category = rng.choices(
            REVIEW_CATEGORIES,
            weights=[cat_weights[c] for c in REVIEW_CATEGORIES],
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
                customer_name=c.name,
                month=m,
                visits=visits,
                purchases=n_purchases,
                spent_eur=_round_eur(spent),
                segment=c.segment,
                pet_size=c.pet_size,
                region=c.region,
                lifestyle=c.lifestyle,
                health_focus=c.health_focus,
                treat_affinity=c.treat_affinity,
                brand_loyalty=c.brand_loyalty,
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


# Per-category cost-of-goods as a fraction of retail price.
# Real pet-store margins vary widely: food categories run thin
# (high cost ratio), accessories / toys / grooming carry fat
# margins (low cost ratio), health + aquarium hardware in
# between. With a flat 0.6 ratio every SKU's profit curve points
# "lower price = more profit" because demand grows faster than
# margin in our engineered data; with category-varying ratios
# the optima shift — some SKUs maximise profit at +5 / +10 % of
# list, others at the discount end.
_COST_RATIO_BY_CATEGORY: dict[str, float] = {
    "dry-food":       0.72,   # tight margins, supplier-dictated
    "wet-food":       0.68,
    "treats":         0.55,
    "dental-treats":  0.50,
    "litter":         0.70,
    # Pet-retail margin reality: non-food categories run 40-55 %
    # gross margin, NOT the 60-70 % the earlier numbers suggested.
    # Higher cost ratios here also pull the max-profit point toward
    # list price for these categories, so the demand curve doesn't
    # always shout "discount everything".
    "accessories":    0.55,
    "toys":           0.52,
    "grooming":       0.50,
    "health":         0.55,
    "aquarium":       0.55,
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
        units = int(data["units"])
        revenue = _round_eur(data["revenue"])
        price = _round_eur(revenue / units) if units > 0 else _round_eur(prod.price_eur)
        out.append(MonthlySale(
            monthly_sale_id=f"{sku}-{month}",
            product_sku=sku,
            month=month,
            units_sold=units,
            revenue_eur=revenue,
            unique_customers=len(data["customers"]),
            pet_type=prod.pet_type,
            category=prod.category,
            brand=prod.brand,
            season=_SEASON_BY_MONTH[month_int],
            price_eur=price,
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

        # Category-dependent cost ratio — food categories carry
        # tight margins (cost ≈ 70 % of retail), accessories /
        # toys / grooming carry fat margins (cost ≈ 30-40 %).
        # Without this variation every profit-curve maximises at
        # the lowest tested price; with it, accessories'/toys'
        # optima shift to the +5/+10 % side.
        cost_ratio = _COST_RATIO_BY_CATEGORY.get(p.category, 0.55)
        unit_cost = _round_eur(p.price_eur * cost_ratio)
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
    """Synthesise per-SKU per-month price snapshots with engineered
    price ↔ demand correlation.

    For Aito's `_estimate units_sold` (the Price view's demand
    curve) to surface a believable elasticity, monthly_sales must
    show low-price months selling more than high-price months.
    The previous approach assigned prices independently from
    demand — Aito's K-NN saw zero correlation and extrapolated
    nonsense at the edges.

    We engineer a target log-log elasticity directly. For each
    month, given the demand deviation from the SKU's median, set
    log(price/list) = -log(units/median) / TARGET_ELASTICITY,
    capped to ±15 % to keep prices in a realistic retail range,
    plus uniform noise (±3 %) so Aito's K-NN doesn't read a crisp
    deterministic ridge as infinite elasticity.

    With TARGET_ELASTICITY = -2.5 and cost ratios ~50 % on
    non-food categories, the demand curve produces an interior
    profit peak near list price for most SKUs — discounting helps
    on some items, raising prices helps on others, neither
    universally. The earlier ±25 % deep-promo bands implied
    elasticity of -5 to -10 and made the curve always shout
    "discount everything", which isn't how pet retail works.
    """
    # Group monthly_sales by SKU to compute per-SKU median units.
    by_sku: dict[str, list[MonthlySale]] = {}
    for ms in monthly_sales:
        by_sku.setdefault(ms.product_sku, []).append(ms)

    TARGET_ELASTICITY = -1.0      # aspirational slope; the K-NN regression
                                  # reads ~1.5-2× steeper because of noise
                                  # truncation at the price caps, landing
                                  # the effective elasticity in the
                                  # realistic -1.5 to -2.5 range
    DEMAND_LOG_CAP = 0.5          # clip log(u/median) to ±0.5 → ~1.65× / 0.6×
    PRICE_NOISE_STD = 0.10        # uniform ~±10 % noise
    MAX_LOG_PRICE_DEV = 0.18      # cap final price swing at ±18 %

    out: list[PriceObservation] = []
    for p in products:
        sku_months = by_sku.get(p.sku, [])
        if not sku_months:
            continue
        units_series = sorted(ms.units_sold for ms in sku_months)
        median_units = max(units_series[len(units_series) // 2], 1)
        list_price = p.price_eur
        for ms in sku_months:
            u = max(ms.units_sold, 1)
            # Demand-driven centre: log(price/list) = log(u/median) / ε.
            # Clip the demand input first so wild outlier months don't
            # anchor a steep ridge.
            log_u_dev = math.log(u / median_units)
            log_u_dev = max(-DEMAND_LOG_CAP, min(DEMAND_LOG_CAP, log_u_dev))
            centre = log_u_dev / TARGET_ELASTICITY
            # Heavy noise uncorrelated with demand. By design this is
            # larger than the deterministic centre's standard deviation
            # so Var(log_price) is noise-dominated. The K-NN
            # regression slope on the resulting data is then close to
            # the target elasticity instead of the much-steeper slope
            # that crisp price-demand bands would produce.
            log_p_dev = centre + rng.uniform(-PRICE_NOISE_STD, PRICE_NOISE_STD)
            log_p_dev = max(-MAX_LOG_PRICE_DEV, min(MAX_LOG_PRICE_DEV, log_p_dev))
            price_ratio = math.exp(log_p_dev)
            price = _round_eur(list_price * price_ratio)
            discount = 1.0 - price_ratio
            out.append(PriceObservation(
                price_observation_id=f"{p.sku}-{ms.month}",
                product_sku=p.sku,
                month=ms.month,
                price_eur=price,
                list_price_eur=_round_eur(list_price),
                discount_pct=round(discount * 100, 1),
            ))
    return out


def backfill_monthly_sales_prices(
    monthly_sales: list[MonthlySale],
    price_history: list[PriceObservation],
) -> None:
    """Overwrite `monthly_sales.price_eur` with the realised price
    from `price_history`, recompute `revenue_eur = price × units`.

    `gen_monthly_sales` initially sets `price_eur = list price`
    (a placeholder). After `gen_price_history` assigns discounts /
    premiums based on demand rank, this pass writes the realised
    price back so monthly_sales reflects the same price Aito's
    `_estimate` will be conditioned on.

    Required for the price-demand correlation to surface in
    `_estimate units_sold` — without this backfill, monthly_sales
    keeps the list price and price_history sits parallel with
    no signal between them.
    """
    price_by_key: dict[tuple[str, str], PriceObservation] = {
        (po.product_sku, po.month): po for po in price_history
    }
    for ms in monthly_sales:
        po = price_by_key.get((ms.product_sku, ms.month))
        if po is None:
            continue
        ms.price_eur = po.price_eur
        ms.revenue_eur = _round_eur(po.price_eur * ms.units_sold)


def gen_winback_campaigns(
    rng: random.Random,
    customers: list[Customer],
    products: list[Product],
) -> list[WinbackCampaign]:
    """Synthesise ~3000 historical re-engagement email campaigns
    sent to customers who had been inactive at send time. Drives the
    Win-back view's `_predict responded` and recoverable-revenue
    roll-up. See ADR 0020.

    Engineered correlations the view surfaces:

      - `lifestyle = premium` responds 4× more often than `budget`
      - Recency `0-90d` responds ~3× more than `180d+`
      - Product matching the customer's segment pet_type responds
        ~3× more than off-segment (cat product for dog_owner = poor)

    Sample shape: pick (customer, product, send_month) triples
    uniformly, weight by engineered response probability, sample
    the outcome. Personas excluded — their stories are
    hand-curated and don't fit the "churned at some point" frame.
    """
    persona_ids = {p.customer_id for p in PERSONAS}

    # Customers eligible for win-back history: anyone with at least
    # one order and a tenure window that allows a gap. Excludes
    # personas and very-new customers.
    eligible = [
        c for c in customers
        if c.customer_id not in persona_ids
        and c.tenure_months >= 4
        and c.total_orders >= 1
    ]
    if not eligible:
        return []

    # Segment → preferred pet_types for the "product matches segment"
    # lift. Mirrors SEGMENT_PET_TYPE_WEIGHTS but as a coarser binary.
    segment_to_pets: dict[str, set[str]] = {
        "dog_owner":          {"dog"},
        "multi_pet":          {"dog", "cat"},
        "cat_owner":          {"cat"},
        "aquarium_owner":     {"aquarium"},
        "small_animal_owner": {"small_animal", "bird"},
    }

    # Send a campaign with this probability per (customer, eligible
    # product) candidate pair; tuned so the total campaign count
    # lands in the ~3000-5000 band (enough for `_predict` to be
    # well-estimated).
    SEND_RATE = 0.0035

    # 24-month send window mirroring _MONTH_WINDOW. Most campaigns
    # cluster in the more-recent half (re-engagement programmes
    # ramp up over time).
    months = _MONTH_WINDOW
    month_weights = [i + 1 for i in range(len(months))]   # linear ramp

    campaigns: list[WinbackCampaign] = []
    counter = 1
    for customer in eligible:
        # How many campaigns to send to this customer. Most get 0-2;
        # heavy-tailed for the marketing-engaged segment.
        n_sends = rng.choices(
            [0, 1, 2, 3, 4],
            weights=[0.55, 0.25, 0.12, 0.05, 0.03],
        )[0]
        if n_sends == 0:
            continue

        preferred_pets = segment_to_pets.get(customer.segment, set())
        for _ in range(n_sends):
            sent_month = rng.choices(months, weights=month_weights)[0]

            # Pick a product to email. Bias slightly toward the
            # customer's preferred pet_type so the engineered
            # "matching products respond better" pattern has enough
            # matched samples to learn from. Off-segment products
            # still occur (failed-campaign realism).
            if preferred_pets and rng.random() < 0.7:
                pool = [p for p in products if p.pet_type in preferred_pets]
            else:
                pool = products
            if not pool:
                continue
            product = rng.choice(pool)

            # Compute recency from a synthetic "days since last
            # order at send time". Engineered to spread across the
            # three buckets with skew toward the medium bucket.
            recency_days = rng.choices(
                [45, 135, 270],   # bucket midpoints
                weights=[0.35, 0.40, 0.25],
            )[0]
            if recency_days <= 90:
                recency_bucket = "0-90d"
            elif recency_days <= 180:
                recency_bucket = "90-180d"
            else:
                recency_bucket = "180d+"

            # Engineered response probability — the load-bearing
            # signal Aito learns from. Multipliers compound; final
            # clipped to [0.005, 0.25] so the rates surface within
            # real-world re-engagement campaign ranges (top
            # email-marketing programmes hit ~20 % open, ~5 % click;
            # we represent the open-equivalent here).
            p = 0.05
            # Lifestyle ↔ premium customers re-engage more.
            p *= {"premium": 2.4, "mid": 1.0, "budget": 0.50}.get(
                customer.lifestyle, 1.0,
            )
            # Recency ↔ recent churners respond more.
            p *= {"0-90d": 1.6, "90-180d": 1.0, "180d+": 0.40}[recency_bucket]
            # Product fit ↔ matching pet_type lifts response.
            matched = bool(preferred_pets) and product.pet_type in preferred_pets
            p *= 3.0 if matched else 0.35
            # Health-focus customers respond to wellness-tagged
            # products specifically.
            if customer.health_focus == "high" and product.dietary in {
                "grain-free", "sensitive", "senior", "weight-control",
            }:
                p *= 1.5
            p = max(0.005, min(0.25, p))

            responded = rng.random() < p
            # Order value if responded — modulated by lifestyle and
            # the product's list price. Naive: ~1-3× product price
            # because customers often add a couple more items.
            order_value = 0.0
            if responded:
                basket_multiplier = {
                    "premium": rng.uniform(1.8, 3.5),
                    "mid":     rng.uniform(1.3, 2.4),
                    "budget":  rng.uniform(1.0, 1.8),
                }.get(customer.lifestyle, 1.5)
                order_value = _round_eur(product.price_eur * basket_multiplier)

            campaigns.append(WinbackCampaign(
                campaign_id=f"WB-{counter:05d}",
                customer_id=customer.customer_id,
                product_sku=product.sku,
                sent_month=sent_month,
                recency_bucket=recency_bucket,
                customer_segment=customer.segment,
                customer_pet_size=customer.pet_size,
                customer_lifestyle=customer.lifestyle,
                customer_health_focus=customer.health_focus,
                product_pet_type=product.pet_type,
                product_category=product.category,
                product_brand=product.brand,
                responded=responded,
                order_value_eur=order_value,
            ))
            counter += 1

    return campaigns


# ── Impressions (recommendation KPI) ────────────────────────────────

# Search-surface vocabulary: query token → catalogue categories it
# pulls from. The token is stored verbatim in `search_query` (a Text
# column) so `where {search_query: {$match: "food"}}` matches it. Kept
# to real category words so the Smart Search re-rank reads naturally.
_SEARCH_TERMS: dict[str, list[str]] = {
    "food":        ["dry-food", "wet-food"],
    "treats":      ["treats", "dental-treats"],
    "toys":        ["toys"],
    "litter":      ["litter"],
    "grooming":    ["grooming"],
    "health":      ["health"],
    "accessories": ["accessories"],
}

# How browsing sessions distribute across surfaces.
_SURFACE_WEIGHTS: dict[str, float] = {
    "search": 0.40, "for_you": 0.30, "category": 0.20, "bought_together": 0.10,
}


def _impression_funnel(
    rng: random.Random,
    product: Product,
    customer: Customer,
    pet_type_weights: dict[str, float],
    cat_bias: dict[str, float] | None,
) -> tuple[bool, bool, bool]:
    """Draw (clicked, added_to_cart, purchased) for one shown product.

    Two deliberately *different* signals, so ranking by clicks differs
    visibly from ranking by purchases (the ADR 0021 demo beat):

      - **Click** is attention-driven — cheap / fun items (toys,
        treats, low price) over-click regardless of fit. Pet relevance
        matters only mildly.
      - **Cart → Purchase** is affinity-driven — pet-type match,
        per-segment category bias, and the customer's brand/dietary/
        loyalty score (`_customer_product_score`) gate it hard, so a
        cat owner essentially never *buys* a dog product even if a
        stray impression shows one.

    Monotone by construction: purchase requires cart requires click.
    """
    pt = pet_type_weights.get(product.pet_type, 0.003)          # 0..~1
    cat = cat_bias.get(product.category, 0.05) if cat_bias else 0.10
    score = _customer_product_score(product, customer)          # ~0.3..6
    life = {"premium": 1.2, "mid": 1.0, "budget": 0.85}[customer.lifestyle]

    # CLICK — attention. Mild pet gate so wrong-pet items still draw
    # the odd curious click, but cheap/fun categories dominate.
    attention = 1.0
    if product.category in ("toys", "treats", "dental-treats"):
        attention *= 1.5
    if product.price_eur < 8:
        attention *= 1.3
    elif product.price_eur > 30:
        attention *= 0.7
    click_p = _clip(0.16 * attention * (0.6 + 0.7 * pt), 0.02, 0.85)

    # CART | CLICK — affinity starts to bite.
    pet_factor = 0.15 + 1.4 * pt                                # 0.15..1.55
    cat_factor = 0.5 + 5.0 * cat                                # ~0.75..2.0
    brand_factor = _clip(score, 0.4, 3.0)
    cart_p = _clip(0.45 * pet_factor * (0.7 + 0.3 * cat_factor) * brand_factor ** 0.4,
                   0.05, 0.92)

    # PURCHASE | CART — strongest affinity gate + lifestyle.
    purchase_p = _clip(0.55 * pet_factor * cat_factor * brand_factor ** 0.5 * life / 2.0,
                       0.05, 0.95)

    clicked = rng.random() < click_p
    added = clicked and rng.random() < cart_p
    purchased = added and rng.random() < purchase_p
    return clicked, added, purchased


def _sessions_for(rng: random.Random, customer: Customer) -> int:
    """How many browsing sessions this customer has. Loosely scaled by
    purchase activity (more orders ⇒ more browsing) with noise, so the
    impressions table mirrors the order distribution without copying it.
    Personas browse more — they carry the For You / Smart Search demo.
    """
    base = 1 + customer.total_orders // 2 + rng.randint(0, 3)
    return max(1, min(base, 16))


def gen_impressions(
    rng: random.Random,
    customers: list[Customer],
    products: list[Product],
) -> list[Impression]:
    """Product impressions with the funnel outcome baked in.

    Reuses the order-generation affinity machinery
    (`_segment_pet_type_weights`, `_category_bias[_for_customer]`,
    `_customer_product_score`) so the products a customer *buys* in
    impressions line up with what they buy in `order_lines` — one
    coherent story across both tables. See ADR 0021.

    Each session shows a mix of affinity-relevant and filler products
    so `goal: {purchased: true}` has both a positive and a negative
    class to rank on: relevant items convert, filler mostly doesn't.
    """
    impressions: list[Impression] = []
    imp_counter = 1
    session_counter = 1

    products_by_cat: dict[str, list[Product]] = {}
    for p in products:
        products_by_cat.setdefault(p.category, []).append(p)
    persona_id_set = {p.customer_id for p in PERSONAS}
    persona_by_id = {p.customer_id: p for p in PERSONAS}

    for customer in customers:
        persona = persona_by_id.get(customer.customer_id)
        if persona is not None and persona.pet_type_weights is not None:
            pet_type_weights = persona.pet_type_weights
        else:
            pet_type_weights = _segment_pet_type_weights(customer.segment, customer.pet_size)
        cat_bias = _category_bias(customer.segment, customer.pet_size)
        if customer.customer_id not in persona_id_set:
            cat_bias = _category_bias_for_customer(cat_bias, customer)

        eligible_months = _MONTH_WINDOW[-(customer.tenure_months + 1):]
        n_sessions = _sessions_for(rng, customer)
        if persona is not None:
            n_sessions = max(n_sessions, 14)  # personas anchor the demo views

        for _ in range(n_sessions):
            session_id = f"SESS-{session_counter:06d}"
            session_counter += 1
            month = rng.choice(eligible_months)
            surface = rng.choices(
                list(_SURFACE_WEIGHTS.keys()),
                weights=list(_SURFACE_WEIGHTS.values()),
            )[0]

            # Build the candidate pool for this session + the query.
            query: str | None = None
            if surface == "search":
                query = rng.choice(list(_SEARCH_TERMS.keys()))
                pool = [p for c in _SEARCH_TERMS[query] for p in products_by_cat.get(c, [])]
            elif surface == "category":
                # One category the customer leans toward, across pet types.
                cat = _pick_product(rng, {"x": products}, "x", cat_bias).category \
                    if cat_bias else rng.choice(list(products_by_cat))
                pool = list(products_by_cat.get(cat, []))
            else:
                # for_you / bought_together — personalised: the whole
                # catalogue, sampled affinity-weighted below.
                pool = list(products)
            if not pool:
                pool = list(products)

            # Show 6-14 distinct products: ~65% affinity-weighted (what a
            # good recommender would surface) + ~35% uniform filler (so
            # there's a negative class). Weighting blends pet-type pref,
            # category bias, and the customer's product score.
            n_shown = min(rng.randint(6, 14), len(pool))
            weights = []
            for p in pool:
                pt = pet_type_weights.get(p.pet_type, 0.003)
                cb = cat_bias.get(p.category, 0.05) if cat_bias else 0.1
                weights.append(max(pt * (0.5 + 5 * cb) * _customer_product_score(p, customer), 1e-4))

            shown: list[Product] = []
            seen: set[str] = set()
            guard = 0
            while len(shown) < n_shown and guard < n_shown * 8:
                guard += 1
                if rng.random() < 0.65:
                    pick = rng.choices(pool, weights=weights, k=1)[0]
                else:
                    pick = rng.choice(pool)
                if pick.sku in seen:
                    continue
                seen.add(pick.sku)
                shown.append(pick)

            for position, product in enumerate(shown):
                clicked, added, purchased = _impression_funnel(
                    rng, product, customer, pet_type_weights, cat_bias,
                )
                impressions.append(Impression(
                    impression_id=f"IMP-{imp_counter:07d}",
                    session_id=session_id,
                    customer_id=customer.customer_id,
                    product_sku=product.sku,
                    surface=surface,
                    month=month,
                    position=position,
                    search_query=query,
                    customer_segment=customer.segment,
                    customer_pet_size=customer.pet_size,
                    customer_lifestyle=customer.lifestyle,
                    customer_health_focus=customer.health_focus,
                    customer_treat_affinity=customer.treat_affinity,
                    customer_brand_loyalty=customer.brand_loyalty,
                    product_pet_type=product.pet_type,
                    product_category=product.category,
                    product_brand=product.brand,
                    clicked=clicked,
                    added_to_cart=added,
                    purchased=purchased,
                ))
                imp_counter += 1

    return impressions


# ── Output ──────────────────────────────────────────────────────────

def _to_json_dict(obj) -> dict:
    """Strip None values from output. Aito treats absent and null-typed
    differently for nullable columns — we send absent for nulls.

    Also drops the in-memory-only `favorite_brands` field from
    `Customer` — it powers the order-generation loop but isn't part
    of the public dataset (and isn't a meaningful column for Aito's
    inference machinery — it's a derived view of brand_loyalty).
    """
    raw = asdict(obj)
    raw.pop("favorite_brands", None)
    return {k: v for k, v in raw.items() if v is not None}


def write_json(path: Path, items: Iterable) -> None:
    payload = [_to_json_dict(o) for o in items]
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def _print_impression_funnel(impressions: list[Impression]) -> None:
    """Print funnel rates and assert the monotonicity invariant
    (purchased ⇒ added_to_cart ⇒ clicked) holds for every row."""
    n = len(impressions) or 1
    clicks = sum(1 for i in impressions if i.clicked)
    carts = sum(1 for i in impressions if i.added_to_cart)
    buys = sum(1 for i in impressions if i.purchased)
    # Invariant: the generator must never emit cart-without-click or
    # purchase-without-cart. Fail loudly here rather than ship bad data.
    broken = [i.impression_id for i in impressions
              if (i.added_to_cart and not i.clicked)
              or (i.purchased and not i.added_to_cart)]
    assert not broken, f"funnel monotonicity violated: {broken[:5]}"
    print()
    print(f"  Impression funnel — click {clicks / n:.1%} → "
          f"cart {carts / n:.1%} → purchase {buys / n:.1%}  "
          f"(target purchase ~12-15%)")


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
    # Now that prices reflect demand-rank discounts/premiums, write
    # the realised price back onto monthly_sales so Aito's
    # `_estimate units_sold` conditions on the same price column.
    # See ADR 0016 §"Price ↔ demand scatter chart".
    backfill_monthly_sales_prices(monthly_sales, price_history)
    # Historical re-engagement campaigns — drives the Win-back
    # view's `_predict responded` per current-churned customer.
    # See ADR 0020.
    winback_campaigns = gen_winback_campaigns(rng, customers, products)

    # Product impressions with the funnel outcome — gives the
    # recommendation surfaces a real conversion KPI to rank on
    # (`_recommend goal: {purchased: true}`). Generated after the
    # customer-aggregate backfill so `_sessions_for` can scale session
    # count by purchase activity. See ADR 0021.
    impressions = gen_impressions(rng, customers, products)

    write_json(DATA_DIR / "products.json", products)
    write_json(DATA_DIR / "customers.json", customers)
    write_json(DATA_DIR / "orders.json", orders)
    write_json(DATA_DIR / "order_lines.json", lines)
    write_json(DATA_DIR / "reviews.json", reviews)
    write_json(DATA_DIR / "customer_months.json", customer_months)
    write_json(DATA_DIR / "monthly_sales.json", monthly_sales)
    write_json(DATA_DIR / "inventory.json", inventory)
    write_json(DATA_DIR / "price_history.json", price_history)
    write_json(DATA_DIR / "winback_campaigns.json", winback_campaigns)
    write_json(DATA_DIR / "impressions.json", impressions)

    # ── Summary print ───────────────────────────────────────────────
    print(f"  products        {len(products):>6}")
    print(f"  customers       {len(customers):>6}")
    print(f"  orders          {len(orders):>6}")
    print(f"  order_lines     {len(lines):>6}")
    print(f"  reviews         {len(reviews):>6}")
    print(f"  customer_months {len(customer_months):>6}")
    print(f"  monthly_sales   {len(monthly_sales):>6}")
    print(f"  inventory       {len(inventory):>6}")
    print(f"  winback         {len(winback_campaigns):>6}")
    print(f"  price_history   {len(price_history):>6}")
    print(f"  impressions     {len(impressions):>6}")
    _print_impression_funnel(impressions)

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
        print(f"    {persona.name.split()[0]:6s} {persona.customer_id}  {formatted}")
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
        p.name.split()[0]: set(_persona_top_pairs(p.customer_id, products, orders, lines))
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
