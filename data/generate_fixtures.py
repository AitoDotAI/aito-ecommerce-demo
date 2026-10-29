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
from typing import Callable, Iterable, Iterator

from data import customer_actions as customer_actions_module
from data import (acquisition, catalogue_events, lifecycle, listing, merchandising, observable, person_data, planted_switches,
                  review_chain, sensitivities, shop_levers, shoppers)
from data.planted_switches import stream

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
            # A cats-only household. With staples (ADR 0027) most of her
            # lines are cat food and litter, so her 5th-ranked pair is a
            # tie at one line, and the segment default's 2 % dog lines
            # could take it and overlap Olli.
            pet_type_weights={"cat": 1.0},
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
    # From this product's reviews, filled after they are generated
    # (ADR 0030, S5). None / "unrated" for a product nobody reviewed.
    avg_rating: float | None = None
    rating_band: str = "unrated"
    # Set only where another product would share the name: "large", "value pack".
    variant: str | None = None


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
    # The one kind of food a dog or cat household buys, if it has a rule:
    # grain-free | sensitive | senior | puppy (ADR 0030, S1).
    diet_rule: str | None = None
    # The pets the household keeps, as it would declare them (ADR 0033).
    pets: tuple[str, ...] = ()
    # ADR 0038: discount, stars, newness, labels → high | mid | low. Hidden.
    sensitivities: dict[str, str] = field(default_factory=dict)
    # ADR 0040: the device and the source of the visit with the first order,
    # and what followed from it (filled after the orders).
    visitor: str | None = None
    # A9: how satisfied this customer tends to be (a standard normal). Hidden; shared cause of NPS, ratings and churn.
    satisfaction: float = 0.0
    first_source: str = "direct"
    joined_month: str | None = None
    first_basket_categories: str | None = None
    became_regular: bool | None = None      # None: joined too late to tell
    # ADR 0039: the month the churn hazard ended the customer's history. Hidden.
    churn_month: str | None = None
    # ADR 0044: behavioural consent, the purchase form, the account and the
    # declared interests (`data/person_data.py`).
    consent_behavioural: bool = True
    pet_profile: bool = True                # declared pets and dog size (about 40 %)
    sex: str | None = None
    postcode_area: str = ""
    delivery_method: str = ""
    loyalty_member: bool = False
    interests: str | None = None


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
    # Forward-looking label: True iff the customer churned and placed no
    # order after this review's month. Backfilled once churn has happened
    # (ADR 0039: churn follows experiences; it never writes the review).
    # Gives the Feedback view a 4th `_predict`, "churn risk from text".
    churn_within_90d: bool = False
    # ADR 0039: the shop replied (40 % of negative reviews, at random), and
    # the order line the review is about.
    replied: bool = False
    order_line: str = ""


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
    pets: str | None                # declared, with a pet profile (ADR 0033): "dog cat"
    dog_size: str | None            # declared, when a dog is among them
    region: str                     # denormalised
    tenure_months_at_month: int     # months since first order at this row's month
    latest_rating: int | None       # most-recent review rating in this month
    latest_sentiment: str | None    # sentiment of that review
    latest_category: str | None     # category of that review
    churned_in_3_months: bool       # the forward target
    # ADR 0039: the latest NPS answer so far, and a negative review written
    # this month or in the 2 before it (and whether the shop replied).
    nps_latest_group: str | None
    had_negative_review: bool
    review_replied: bool


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
    # Last calendar month's units for this SKU (0 if it sold nothing),
    # and both months as sales ranges. The Demand forecast conditions on
    # last month; its accuracy is scored on ranges against the naive
    # "same range as last month" rule. See ADR 0014 §Correction.
    units_last_month: int
    units_bucket: str
    units_last_month_bucket: str
    product_state: str          # link → product_states: this product in this month (ADR 0032)
    # ADR 0045: price ÷ that month's list price, the offer band, and the
    # product's recorded impressions that month.
    price_index: float = 1.0
    discount_band: str = "none"
    showings: int = 0
    # ADR 0049: the list price and the listing that month, copied from the state (`_estimate` cannot
    # read a linked field), and the units against the product's own mean.
    list_price_index: float = 1.0
    image_count: str = "2-3"
    description_quality: str = "ok"
    ad_level: str = "none"
    units_index: float | None = None
    showings_index: float | None = None


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
    # The (pet, category) the customer bought most, at least three times,
    # e.g. "dog/dry-food"; "none" if nothing reached three. ADR 0027: a send
    # in the customer's staple category responds 2.5x as often, so the page
    # needs this as evidence to learn which product to send.
    customer_staple_category: str
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
    """One product shown in a context, with the funnel outcome recorded
    (ADR 0021). Who, when and where live on the context (ADR 0033).

    Funnel monotonicity invariant: purchased ⇒ added_to_cart ⇒ clicked.
    Enforced at generation; asserted by `./do aito-check`.
    """
    impression_id: str             # "IMP-NNNNNNN"
    context: str                   # link → contexts.context_id
    product_sku: str               # link → products.sku
    product_state: str             # link → product_states (ADR 0032)
    position: int                  # 0-based slot within its placement
    # ADR 0045: the part of the page: buy_again (what the household came
    # for), list (the shop's ranked list) or checkout (bought together).
    placement: str = "list"
    just_bought: bool = False      # the product was in the customer's last order (S8)
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
    # ADR 0030, for the interactive shop: this order's SKUs, the previous
    # order's SKUs (recency, S8), and the kit durables owned before it.
    skus: str = ""
    prev_skus: str | None = None
    owned_before: str | None = None


@dataclass
class OrderLine:
    line_id: str
    order_id: str
    product_sku: str
    qty: int
    returned: bool
    # ADR 0032: link → product_states, the product as it was that month.
    product_state: str | None = None
    # ADR 0039: the delivery of this line's order was late or damaged.
    incident: bool = False


@dataclass
class NpsResponse:
    """A survey answer after an order (ADR 0039, R3): 0–10, and its group."""
    nps_response_id: str
    customer: str                   # link → customers.customer_id
    surveyed_order: str             # link → orders.order_id, the order surveyed
    month: str
    score: int
    nps_group: str                  # promoter (9–10) | passive (7–8) | detractor (0–6)
    # What the shop can read beside the answer. `relate` cannot follow the order to its
    # lines (one-to-many), so the order's first product, as it was that month, is here:
    product_state: str              # link → product_states
    wrote_negative_review: bool     # the respondent reviewed a product of this order at 1–2 stars


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

    name_variants(products)
    return products


# Categories where the Filling demo's "missing fields" framing is
# meaningful — i.e. where weight_kg, dietary, and tax_class are all
# normally populated. Used by the null-injection step in `gen_products`
# and by the signal #4 test.
FILLABLE_CATEGORIES: set[str] = {
    "dry-food", "wet-food", "treats", "dental-treats", "litter",
}



# What tells two otherwise identical products apart, by category (data release 2:
# a merchant reads two SKUs with one name as a duplicate).
VARIANTS_BY_CATEGORY: dict[str, tuple[str, ...]] = {
    "accessories": ("small", "medium", "large", "extra large", "natural wood", "grey"),
    "toys":        ("small", "medium", "large", "blue", "red", "green"),
    "dry-food":    ("classic recipe", "light recipe", "value pack", "multipack", "family pack", "trial pack"),
    "wet-food":    ("classic recipe", "light recipe", "multipack", "value pack", "family pack", "trial pack"),
    "treats":      ("classic", "soft", "crunchy", "value pack", "multipack", "trial pack"),
    "dental-treats": ("small dogs", "medium dogs", "large dogs", "value pack", "multipack", "trial pack"),
    "litter":      ("unscented", "lavender scent", "value pack", "multipack", "fresh scent", "trial pack"),
}
PACK_VARIANTS = ("single", "twin pack", "triple pack", "value pack", "refill", "starter pack")


def name_variants(products: list[Product]) -> None:
    """Products sharing a name get a distinguishing variant, in SKU order:
    "Trixie Hideout, small", "Trixie Hideout, medium". No RNG draw, so
    nothing else in the data moves. The variant follows a comma, which
    `lifecycle.item_type` drops."""
    by_name: dict[str, list[Product]] = {}
    for p in products:
        by_name.setdefault(p.name, []).append(p)
    for same in by_name.values():
        if len(same) < 2:
            continue
        variants = VARIANTS_BY_CATEGORY.get(same[0].category, PACK_VARIANTS)
        assert len(same) <= len(variants), f"{len(same)} products named {same[0].name!r}"
        for p, variant in zip(sorted(same, key=lambda p: p.sku), variants):
            p.variant = variant
            p.name = f"{p.name}, {variant}"


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
        # Two of the three flavours already say it ("Daily Dental",
        # "Puppy Dental"); don't print "Daily Dental Dental Treats".
        parts.append("Treats" if flavour.endswith("Dental") else "Dental Treats")
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



def assign_sources_and_sensitivities(customers: list[Customer]) -> None:
    """Each customer's first source (ADR 0040) and their hidden sensitivities
    (ADR 0038), which depend on it (F3). Own RNGs per customer, so the
    generator's other draws stay where they were."""
    for c in customers:
        c.first_source = acquisition.draw_first_source(stream(RNG_SEED, "first-source", c.customer_id))
        c.sensitivities = sensitivities.draw_sensitivities(
            stream(RNG_SEED, "sensitivities", c.customer_id),
            c.lifestyle, c.health_focus, c.brand_loyalty, c.first_source)


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

    # ADR 0032, P5: a large dog's household buys big bags, a small dog's small ones.
    score *= catalogue_events.pack_fit(product, customer.pet_size)

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
    demand_factor: "Callable[[str], float] | None" = None,
) -> Product:
    """Pick a product of `pet_type`, weighted by category_bias and, when
    given, by `demand_factor(sku)` (how much a promotion lifts it this month)."""
    pool = products_by_pet[pet_type]
    if not pool:
        # Should not happen if products span every pet_type — but if it
        # does, fall back to any product so the generator never deadlocks.
        return rng.choice(next(iter(products_by_pet.values())))
    if category_bias is None and demand_factor is None:
        return rng.choice(pool)
    weights = [
        (category_bias.get(p.category, 0.05) if category_bias is not None else 1.0)
        * (demand_factor(p.sku) if demand_factor is not None else 1.0)
        for p in pool
    ]
    return rng.choices(pool, weights=weights, k=1)[0]


def _customer_preference_substitute(
    chosen: Product,
    products_by_pet_cat: dict[tuple[str, str], list[Product]],
    customer: Customer,
    persona_ids: set[str],
    line_counter: int,
    demand_factor: "Callable[[str], float] | None" = None,
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
            if demand_factor is None:
                return sub_rng.choice(favorite_in_slice)
            return sub_rng.choices(favorite_in_slice,
                                   weights=[demand_factor(p.sku) for p in favorite_in_slice], k=1)[0]

    # General customer-preference substitution. Higher base rate
    # than the prior segment-level affinity (0.50) — customer-level
    # traits are stable across the customer's entire purchase
    # history, so the substitution should be the dominant signal.
    if sub_rng.random() > 0.65:
        return chosen

    # Weight every same-slice candidate by the customer's score; pick
    # via cumulative weighted choice. Empty / all-zero weights ⇒
    # keep the original.
    # ADR 0027: a promotion lifts a product here too; without it, this
    # re-pick diluted the price response to about a sixth of its size.
    weights = [max(_customer_product_score(p, customer), 0.01)
               * (demand_factor(p.sku) if demand_factor is not None else 1.0)
               for p in same_slice]
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


def _order_months(rng: random.Random, eligible: list[str], n: int) -> list[str]:
    """A customer's order months in time order, distinct while the window allows."""
    if n <= len(eligible):
        return sorted(rng.sample(eligible, n))
    return sorted(rng.choice(eligible) for _ in range(n))


def _pick_of_type(
    rng: random.Random,
    products_by_pet: dict[str, list[Product]],
    pet: str,
    kind: str,
    customer: Customer,
) -> Product | None:
    """A product of item type `kind` for `pet`, weighted by the customer's tastes."""
    pool = [p for p in products_by_pet.get(pet, []) if lifecycle.item_type(p.name, p.brand) == kind]
    if not pool:
        return None
    return rng.choices(pool, weights=[_customer_product_score(p, customer) for p in pool], k=1)[0]


def _pick_staple(
    rng: random.Random,
    products_by_pet_cat: dict[tuple[str, str], list[Product]],
    pet: str,
    category: str,
    customer: Customer,
    exclude: str | None,
    novelty: Callable[[str], float],
    avoid_poorly_made: bool = False,
) -> Product | None:
    """The consumable a customer settles on for one pet and category,
    keeping the household's diet rule (ADR 0030, S1). Someone leaving a
    poorly made one moves to one that isn't (S5). A product new this month
    draws new customers and switchers (`novelty`, ADR 0032 P2).

    None when nothing on sale this month keeps the rule (a seed's catalogue
    may have no puppy wet food, say): the household has no such staple yet."""
    pool = [p for p in products_by_pet_cat.get((pet, category), [])
            if lifecycle.is_staple(p, pet) and p.sku != exclude
            and shoppers.keeps_diet_rule(p.name, pet, category, customer.diet_rule)
            and not (avoid_poorly_made and _is_poor(p.sku))]
    if not pool:
        return None
    return rng.choices(pool, weights=[_customer_product_score(p, customer) * novelty(p.sku) for p in pool], k=1)[0]


@dataclass
class OrderHistory:
    """What the session loop draws: what a shop records, and what it can't see."""
    orders: list[Order]
    lines: list[OrderLine]
    reviews: list[Review]
    nps: list[NpsResponse]
    experience_of: dict[str, str]          # line_id → bad | ok | good (hidden: the answer key)
    states: list[catalogue_events.ProductState]
    contexts: list[observable.Context]     # recorded: consenting customers' sessions only
    impressions: list[Impression]


@dataclass
class _Session:
    """One customer's session, recorded or not (ADR 0044: consent decides)."""
    context: observable.Context
    impressions: list[Impression]
    purchased: bool


@dataclass
class _Shop:
    """What every customer's sessions read and write, month by month."""
    products: list[Product]
    promotions: lifecycle.Promotions
    events: catalogue_events.CatalogueEvents
    by_pet_in: dict[str, dict[str, list[Product]]]
    by_pet_cat_in: dict[str, dict[tuple[str, str], list[Product]]]
    by_cat_in: dict[str, dict[str, list[Product]]]
    product_of: dict[str, Product]
    stars: review_chain.StarsSoFar
    persona_ids: set[str]
    phrases: dict[str, list[Product]]
    phrases_of: dict[str, list[str]]
    stock: shop_levers.StockBook
    # The month's product states, drawn at its start from what happened before.
    states: dict[str, dict[str, catalogue_events.ProductState]] = field(default_factory=dict)
    units: dict[str, Counter] = field(default_factory=dict)        # month → sku → units sold
    # Per customer, in order: (order, its lines, their experiences), reviews,
    # NPS answers, sessions.
    orders_of: dict[str, list[tuple[Order, list[OrderLine], list[str]]]] = field(default_factory=dict)
    reviews_of: dict[str, list[Review]] = field(default_factory=dict)
    nps_of: dict[str, list[NpsResponse]] = field(default_factory=dict)
    sessions_of: dict[str, list[_Session]] = field(default_factory=dict)

    def begin_month(self, month: str) -> None:
        """This month's product states, from the stars, labels, stock and prices
        known at its start (ADR 0038, ADR 0045)."""
        skus = [p.sku for p in self.products if self.events.on_sale(p.sku, month)]
        previous = _add_months(month, -1)
        labels = shop_levers.labels_for_month(RNG_SEED, month, skus, self.units.get(previous) if month != _MONTH_WINDOW[0] else None,
                                              {p.sku: p.category for p in self.products})
        low = {sku for sku in skus if self.stock.opens_low(sku, month)}
        stars = {sku: (self.stars.band(sku), self.stars.count(sku)) for sku in skus if self.stars.count(sku)}
        states = catalogue_events.states_for_month(RNG_SEED, month, self.products, self.events,
                                                   self.promotions.discount, stars, labels, low)
        self.states[month] = {st.product_sku: st for st in states}
        self.units[month] = Counter()

    def close_month(self, month: str) -> None:
        """The month's reviews become stars; its units leave the shelves."""
        self.stars.close_month()
        for sku in self.states[month]:
            self.stock.close_month(sku, self.units[month][sku])


class _ChurnClock:
    """One customer's monthly churn hazard (ADR 0039, R4).

    The base hazard is `_churn_propensity`, spread over the customer's window
    from their first order to the frozen today. Each bad experience raises it
    for `CHURN_RISE_MONTHS`. One uniform per month from the customer's own RNG,
    so a null that changes the hazard changes only when the clock stops."""

    def __init__(self, customer: Customer, n_orders: int, first_month: str, never: bool):
        self.rng = stream(RNG_SEED, "churn", customer.customer_id)
        p = _churn_propensity(customer, n_orders)
        window = max(1, _months_between(first_month, DEMO_TODAY_YYYYMM))
        self.base = 1.0 - (1.0 - p) ** (1.0 / window)
        self.walked = first_month
        self.month: str | None = None          # the month the customer churned
        self.never = never
        self.trait_factor = review_chain.churn_factor(customer.satisfaction)
        self.rises: list[tuple[str, float]] = []

    def rise(self, month: str, factor: float) -> None:
        self.rises.append((month, factor))

    def hazard(self, month: str) -> float:
        h = self.base * self.trait_factor
        for since, factor in self.rises:
            if since < month <= _add_months(since, review_chain.CHURN_RISE_MONTHS):
                h *= factor
        return min(1.0, h)

    def churned_by(self, month: str) -> bool:
        """Walk the clock up to and including `month`; whether the customer has churned."""
        while self.month is None and self.walked < month:
            self.walked = _add_months(self.walked, 1)
            if self.rng.random() < self.hazard(self.walked) and not self.never:
                self.month = self.walked
        return self.month is not None


def _review_text(rng: random.Random, category: str, pet: str) -> str:
    """A templated review in `category`'s words (ADR 0012)."""
    text = rng.choice(_REVIEW_TEMPLATES[category])
    for slot in ("timing", "pack_quality", "detail", "product_noun",
                 "scent", "reaction", "quality_adj", "action", "size",
                 "fit_adj", "accuracy_adj", "feature", "question_clause",
                 "condition"):
        placeholder = "{" + slot + "}"
        if placeholder in text:
            text = text.replace(placeholder, rng.choice(_REVIEW_VOCAB[slot]))
    return text.replace("{pet}", pet)


def _is_poor(sku: str) -> bool:
    return review_chain.quality(sku) == "poor"


def gen_orders_and_lines(
    customers: list[Customer],
    products: list[Product],
    promotions: lifecycle.Promotions,
    events: catalogue_events.CatalogueEvents,
) -> OrderHistory:
    """Every customer's sessions, and the orders their purchases make (ADR 0045).

    The shop runs month by month. At a month's start its product states are
    drawn from what happened before (stars, labels, stock). Each customer's
    history is a generator (`_customer_life`) that yields the month of its
    next session; once every session of a month is drawn, its reviews become
    stars and its units leave the shelves. Each customer draws from their own
    RNGs, so the order in which customers are resumed doesn't change anything.

    The engineered signals of ADR 0002 stay: large-breed dog owners' cat
    share, the dog-food → dental-treats lift, the personas' separation, the
    null-attribute pile and the returned share.
    """
    by_pet_in: dict[str, dict[str, list[Product]]] = {}
    by_pet_cat_in: dict[str, dict[tuple[str, str], list[Product]]] = {}
    by_cat_in: dict[str, dict[str, list[Product]]] = {}
    # ADR 0032: each month's catalogue holds only what is on sale then, so
    # no draw below can pick a product before its launch.
    for m in _MONTH_WINDOW:
        by_pet_in[m] = {pt: [] for pt in PET_TYPES}
        by_pet_cat_in[m], by_cat_in[m] = {}, {}
        for p in products:
            if events.on_sale(p.sku, m):
                by_pet_in[m][p.pet_type].append(p)
                by_pet_cat_in[m].setdefault((p.pet_type, p.category), []).append(p)
                by_cat_in[m].setdefault(p.category, []).append(p)
    phrases = shoppers.query_phrases(products)
    phrases_of: dict[str, list[str]] = {}
    for phrase, matching in phrases.items():
        for p in matching:
            phrases_of.setdefault(p.sku, []).append(phrase)
    shop = _Shop(products, promotions, events, by_pet_in, by_pet_cat_in, by_cat_in, {p.sku: p for p in products},
                 review_chain.StarsSoFar(), {p.customer_id for p in PERSONAS}, phrases, phrases_of,
                 shop_levers.StockBook(RNG_SEED))
    persona_of = {p.customer_id: p for p in PERSONAS}

    lives = [_customer_life(c, persona_of.get(c.customer_id), shop) for c in customers]
    waiting: dict[str, list[int]] = {}
    for i, life in enumerate(lives):
        first = next(life, None)
        if first is not None:
            waiting.setdefault(first, []).append(i)
    for month in _MONTH_WINDOW:
        shop.begin_month(month)
        for i in sorted(waiting.pop(month, [])):
            following = next(lives[i], None)
            if following is not None:
                assert following > month, f"{customers[i].customer_id} went back from {month} to {following}"
                waiting.setdefault(following, []).append(i)
        shop.close_month(month)
    assert not waiting, f"sessions planned outside the window: {sorted(waiting)}"
    return _number_history(customers, shop)


def _number_history(customers: list[Customer], shop: _Shop) -> OrderHistory:
    """Final ids, customer by customer and month by month, so a persona's
    orders keep the lowest ids (CUST-00001's are ORD-00001…). Sessions before
    a customer's first order are a visitor's (no `customer`, ADR 0040); the one
    with it is marked `first_order`. Only consenting customers' sessions are
    recorded (ADR 0044)."""
    states = [st for month in _MONTH_WINDOW for st in shop.states[month].values()]
    history = OrderHistory([], [], [], [], {}, states, [], [])
    line_id: dict[str, str] = {}
    order_id: dict[str, str] = {}
    for c in customers:
        for order, lines, experiences in shop.orders_of.get(c.customer_id, []):
            order_id[order.order_id] = f"ORD-{len(history.orders) + 1:05d}"
            order.order_id = order_id[order.order_id]
            history.orders.append(order)
            for line, experience in zip(lines, experiences):
                line_id[line.line_id] = f"LN-{len(history.lines) + 1:06d}"
                line.line_id, line.order_id = line_id[line.line_id], order.order_id
                history.lines.append(line)
                history.experience_of[line.line_id] = experience
    for c in customers:
        for review in shop.reviews_of.get(c.customer_id, []):
            review.review_id = f"REV-{len(history.reviews) + 1:05d}"
            review.order_line = line_id[review.order_line]
            history.reviews.append(review)
        for answer in shop.nps_of.get(c.customer_id, []):
            answer.nps_response_id = f"NPS-{len(history.nps) + 1:05d}"
            answer.surveyed_order = order_id[answer.surveyed_order]
            history.nps.append(answer)
    for c in customers:
        joined = False
        for session in shop.sessions_of.get(c.customer_id, []):
            session.context.first_order = session.purchased and not joined
            if not joined and not session.purchased:
                session.context.customer = None      # still a visitor
            joined |= session.purchased
            if not c.consent_behavioural:
                continue
            session.context.visitor = c.customer_id     # the device's id is assigned with the visitors'
            session.context.context_id = f"SESS-{len(history.contexts) + 1:06d}"
            history.contexts.append(session.context)
            for imp in session.impressions:
                imp.impression_id = f"IMP-{len(history.impressions) + 1:07d}"
                imp.context = session.context.context_id
                history.impressions.append(imp)
    for context in history.contexts:
        context.weekday = random.Random(f"weekday:{context.context_id}").choice(WEEKDAYS)
    return history


def _customer_life(customer: Customer, persona: Persona | None, shop: _Shop) -> Iterator[str]:
    """One customer's sessions: a generator that yields the month of its next
    session, and draws it when the shop resumes it in that month.

    ADR 0027: the customer's life with their pets. Staples are restocked; each
    pet starts with a kit whose add-ons follow; durables are bought once.
    ADR 0045: every purchase is a showing in a session (`_draw_session`), and
    a session's purchases are its order. ADR 0039: each line's experience
    comes from the product's quality; it may be reviewed, the order may be
    surveyed, and a bad one raises the churn hazard. ADR 0040: a regular
    customer orders at least 3 times in their first 6 months."""
    cid = customer.customer_id
    rng = stream(RNG_SEED, "orders", cid)
    experience_rng, incident_rng = stream(RNG_SEED, "experience", cid), stream(RNG_SEED, "incident", cid)
    review_rng, reply_rng = stream(RNG_SEED, "review", cid), stream(RNG_SEED, "reply", cid)
    nps_rng = stream(RNG_SEED, "nps", cid)
    # How many sessions, and in which months, from the customer's own RNG.
    months_rng = random.Random(f"months:{cid}")
    n_orders = persona.target_orders if persona is not None else _orders_per_customer(months_rng, customer)

    if persona is not None and persona.pet_type_weights is not None:
        pet_type_weights = persona.pet_type_weights
    else:
        pet_type_weights = _segment_pet_type_weights(customer.segment, customer.pet_size)
    cat_bias = _category_bias(customer.segment, customer.pet_size)
    # Personas keep their segment-level bias: their top-5 pairs stay separated.
    if persona is None:
        cat_bias = _category_bias_for_customer(cat_bias, customer)

    eligible_months = _MONTH_WINDOW[-(customer.tenure_months + 1):]
    # At most one session a month, so at most one order.
    n_orders = min(n_orders, len(eligible_months))
    plan = _order_months(months_rng, eligible_months, n_orders)
    if persona is not None and plan[-1] != eligible_months[-1]:
        # A persona anchors the demo's default views, so it must not read
        # as churned: its history reaches the latest month by rule.
        plan = plan[1:] + [eligible_months[-1]]
    pets = lifecycle.main_pets(pet_type_weights)
    customer.pets = tuple(pets)
    # ADR 0030: the household's diet rule (personas keep none), from its own seeded RNG.
    if persona is None:
        customer.diet_rule = shoppers.assign_diet_rule(random.Random(f"diet:{cid}"), pets)
    staple_cats = {pet: lifecycle.staple_categories(rng, pet) for pet in pets}
    # ADR 0040: some households start their staples with their second order.
    first_staple_order = 0 if persona is not None or (
        stream(RNG_SEED, "first-staple", cid).random() < acquisition.FIRST_ORDER_STAPLE_P) else 1
    life = _Household(customer, persona, pet_type_weights, cat_bias, pets, staple_cats, first_staple_order,
                      story_rng=random.Random(f"story:{cid}"), visit_rng=stream(RNG_SEED, "visit-source", cid))
    customer.satisfaction = review_chain.satisfaction(RNG_SEED, cid)
    churn = _ChurnClock(customer, n_orders, plan[0], never=persona is not None)
    shop.orders_of[cid], shop.reviews_of[cid], shop.nps_of[cid], shop.sessions_of[cid] = [], [], [], []

    while plan:
        month = plan.pop(0)
        if churn.churned_by(month):
            break
        yield month
        order_ref = f"{cid}#{len(shop.orders_of[cid])}"
        session, bought = _draw_session(shop, life, rng, month, len(shop.sessions_of[cid]))
        shop.sessions_of[cid].append(session)
        if not bought:
            continue     # a visit without a purchase: no order this month
        this_orders_lines = _order_lines(rng, customer, order_ref, month, bought)
        for ln in this_orders_lines:
            shop.units[month][ln.product_sku] += ln.qty
        life.record_order(month, [p for p, _ in bought], [st for _, st in bought])
        line_tokens = [f"{p.pet_type}_{p.category.replace('-', '')}" for p, _ in bought]
        order = Order(order_id=order_ref, customer_id=cid, month=month,
                      total_eur=_round_eur(sum(shop.events.list_price(ln.product_sku, month) * ln.qty
                                               for ln in this_orders_lines)),
                      line_categories=" ".join(line_tokens),
                      skus=" ".join(ln.product_sku for ln in this_orders_lines),
                      prev_skus=life.prev_skus, owned_before=session.context.owned)
        life.prev_skus = order.skus

        # ADR 0039: what the order was like, and what followed from it.
        incident = incident_rng.random() < review_chain.INCIDENT_P
        experiences = []
        replied_negative = False
        wrote_negative = False
        for ln in this_orders_lines:
            ln.incident = incident
            experience = review_chain.draw_experience(experience_rng, ln.product_sku)
            experiences.append(experience)
            if planted_switches.ON["A7"]:
                # After the household has recorded the order, so no later purchase depends on it: a line
                # that went badly is also returned, and a share of the rest is not, to keep the returned
                # share near 2.75 %.
                u = stream(RNG_SEED, "return_by_experience", ln.line_id).random()
                if experience == "bad":
                    ln.returned = ln.returned or u < review_chain.BAD_EXPERIENCE_RETURN_P
                elif ln.returned and u < review_chain.RETURN_THIN_P:
                    ln.returned = False
            drawn = review_chain.draw_review(review_rng, reply_rng, experience, customer.satisfaction) \
                if planted_switches.REVIEWS_WRITTEN else None
            if drawn is None:
                continue
            replied_negative |= drawn.replied
            wrote_negative |= drawn.rating <= 2
            shop.reviews_of[cid].append(Review(
                review_id="", customer_id=cid, product_sku=ln.product_sku, rating=drawn.rating,
                text=_review_text(review_rng, drawn.category, shop.product_of[ln.product_sku].pet_type),
                category=drawn.category, sentiment=_sentiment_for(drawn.rating),
                assigned_to=REVIEW_CATEGORY_TO_AGENT[drawn.category], created_at=month,
                replied=drawn.replied, order_line=ln.line_id))
            shop.stars.add(ln.product_sku, drawn.rating)
        experience = review_chain.order_experience(experiences)
        score = review_chain.nps_score(nps_rng, experience, incident, replied_negative, customer.satisfaction)
        if score is not None:
            shop.nps_of[cid].append(NpsResponse(
                nps_response_id="", customer=cid, surveyed_order=order_ref, month=month,
                score=score, nps_group=review_chain.nps_group(score),
                product_state=this_orders_lines[0].product_state, wrote_negative_review=wrote_negative))
        if experience == "bad":
            churn.rise(month, review_chain.churn_rise(replied_negative))
        if planted_switches.ON["A6"] and incident:
            churn.rise(month, review_chain.INCIDENT_CHURN_RISE)
        for ln in this_orders_lines:
            if ln.returned and planted_switches.ON["A7"]:
                churn.rise(month, review_chain.RETURN_CHURN_RISE)
        first_order = not shop.orders_of[cid]
        shop.orders_of[cid].append((order, this_orders_lines, experiences))

        if first_order and persona is None:
            # ADR 0040, F4 and F5: whether this customer becomes a regular.
            regular_rng = stream(RNG_SEED, "regular", cid)
            staple_first = any(acquisition.is_staple_line(p) for p, _ in bought)
            regular = regular_rng.random() < acquisition.regular_probability(customer.first_source, staple_first)
            plan = acquisition.plan_first_months(regular_rng, plan, month, eligible_months, regular)

    # The clock runs to today: the answer key records when the customer left.
    churn.churned_by(DEMO_TODAY_YYYYMM)
    customer.churn_month = churn.month


def _order_lines(rng: random.Random, customer: Customer, order_ref: str, month: str,
                 bought: list[tuple[Product, catalogue_events.ProductState]]) -> list[OrderLine]:
    """A session's purchases as order lines. Quantities don't read price: an
    offer acts on the chance to buy (ADR 0045)."""
    lines = []
    for product, _ in bought:
        qty = rng.choices([1, 2, 3], weights=[0.78, 0.18, 0.04])[0]
        # Budget customers return more, premium less; dental treats rarely (2.5-3.5 % overall).
        returned_rate = 0.02 if product.category == "dental-treats" else \
            {"premium": 0.018, "mid": 0.030, "budget": 0.042}[customer.lifestyle]
        lines.append(OrderLine(line_id=f"{order_ref}.{len(lines)}", order_id=order_ref, product_sku=product.sku,
                               qty=qty, returned=rng.random() < returned_rate,
                               product_state=f"{product.sku}-{month}"))
    return lines


class _Household:
    """What one customer's sessions remember between months: the staples they
    settled on, the kit they own, their last order, and what they bought."""

    def __init__(self, customer: Customer, persona: Persona | None, pet_type_weights: dict[str, float],
                 cat_bias: dict[str, float] | None, pets: list[str], staple_cats: dict[str, tuple[str, ...]],
                 first_staple_order: int, story_rng: random.Random, visit_rng: random.Random):
        self.customer, self.persona = customer, persona
        self.pet_type_weights, self.cat_bias, self.pets = pet_type_weights, cat_bias, pets
        self.staple_cats, self.first_staple_order = staple_cats, first_staple_order
        self.story_rng, self.visit_rng = story_rng, visit_rng
        self.staples: dict[tuple[str, str], Product] = {}
        self.owned_durables: set[str] = set()
        self.owned_tokens: set[str] = set()          # per pet: "small_animal_cage"
        self.prev_skus: str | None = None
        self.orders = 0
        self.bought: list[tuple[str, catalogue_events.ProductState]] = []   # (month, state) per purchase
        self.pets_bought: list[tuple[str, str]] = []                        # (month, pet type) per purchase

    def record_order(self, month: str, products: list[Product], states: list) -> None:
        self.orders += 1
        for product, state in zip(products, states):
            kind = lifecycle.item_type(product.name, product.brand)
            if kind in lifecycle.DURABLE_TYPES:
                self.owned_durables.add(kind)
                self.owned_tokens.add(shoppers.token(product.pet_type, kind))
            self.bought.append((month, state))
            self.pets_bought.append((month, product.pet_type))


def _buy_again(shop: _Shop, life: _Household, rng: random.Random, month: str) -> list[tuple[Product, str]]:
    """What the household came for, each with its intent (`merchandising.INTENT_P`):
    the old order's lifecycle lines (ADR 0027, ADR 0030), now shown and bought
    with odds (ADR 0045)."""
    customer, events = life.customer, shop.events
    products_by_pet, products_by_pet_cat = shop.by_pet_in[month], shop.by_pet_cat_in[month]
    # A fresh pick of a staple: a new one pulls (ADR 0032, P2), and the stars so far move it (R5).
    novelty = lambda sku: events.pick_factor(sku, month) * shop.stars.pick_factor(sku)
    wanted: list[tuple[Product, str]] = []

    def want(product: Product | None, intent: str) -> None:
        if product is not None and all(product.sku != p.sku for p, _ in wanted):
            wanted.append((product, intent))

    if life.orders == 0:
        for pet in life.pets:
            for kind in lifecycle.STARTER_KITS.get(pet, ()):
                want(_pick_of_type(rng, products_by_pet, pet, kind, customer), "kit")
    # Staples: chosen the first time, then restocked (sometimes switched).
    for pet in life.pets if life.orders >= life.first_staple_order else ():
        for category in life.staple_cats[pet]:
            key = (pet, category)
            if key not in life.staples:
                first = _pick_staple(rng, products_by_pet_cat, pet, category, customer, exclude=None, novelty=novelty)
                if first is not None:
                    life.staples[key] = first
                    want(first, "first")
                continue
            current = life.staples[key]
            poor = _is_poor(current.sku)
            # A poorly made staple is dropped more often (S5); a price rise or a
            # rival's launch makes regulars reconsider (ADR 0032).
            switch_p = min(1.0, (shoppers.POOR_SWITCH_P if poor else lifecycle.SWITCH_P)
                           * events.reconsider_factor(current.sku, month))
            if rng.random() < lifecycle.RESTOCK_P and rng.random() < switch_p:
                rivals = [shop.product_of[r] for r in events.rivals(current.sku, month)
                          if catalogue_events.SWITCH_TO_RIVAL and lifecycle.is_staple(shop.product_of[r], pet)
                          and shoppers.keeps_diet_rule(shop.product_of[r].name, pet, category, customer.diet_rule)]
                if rivals:
                    life.staples[key] = rng.choices(
                        rivals, weights=[_customer_product_score(p, customer) for p in rivals], k=1)[0]
                else:
                    # Nothing else keeps the rule this month: they stay with what they have.
                    life.staples[key] = _pick_staple(rng, products_by_pet_cat, pet, category, customer,
                                                     exclude=current.sku, novelty=novelty,
                                                     avoid_poorly_made=poor) or current
                want(life.staples[key], "first")
            else:
                want(current, "restock")
    # An add-on the kit implies, not yet owned: mostly the next one (S2).
    if life.orders > 0 and rng.random() < lifecycle.ADD_ON_P:
        needing = [pet for pet in life.pets
                   if any(k not in life.owned_durables for k in lifecycle.ADD_ONS.get(pet, ()))]
        if needing:
            pet = rng.choice(needing)
            kind = shoppers.next_add_on(life.story_rng, lifecycle.ADD_ONS[pet], life.owned_durables)
            want(_pick_of_type(rng, products_by_pet, pet, kind, customer), "add_on")
    # A gift before Christmas, care in summer (S4): one line for one of the pets.
    for line_p, categories in ((shoppers.GIFT_LINE_P, shoppers.GIFT_CATEGORIES),
                               (shoppers.CARE_LINE_P, shoppers.CARE_CATEGORIES)):
        if life.pets and life.story_rng.random() < line_p.get(int(month[5:]), 0.0):
            pet = life.story_rng.choice(life.pets)
            seasonal = [p for c in categories for p in products_by_pet_cat.get((pet, c), [])]
            if seasonal:
                want(life.story_rng.choices(seasonal, weights=[novelty(p.sku) for p in seasonal], k=1)[0], "seasonal")
    return wanted


def _price_and_state_odds(shop, customer: Customer, product: Product, state) -> tuple[float, float, float]:
    """(click, cart-and-purchase, purchase-only) odds from the product's state,
    its price and its quality: every price effect sits here (ADR 0045)."""
    click, odds, purchase_only = sensitivities.state_odds(state, customer.sensitivities)
    price = merchandising.list_price_odds(
        shop.events.raised_since(product.sku, state.month),
        review_chain.rating_elasticity(state.rating_band, shop.promotions.elasticity[product.sku]))
    quality = review_chain.POOR_QUALITY_ODDS if planted_switches.ON["quality"] and _is_poor(product.sku) else 1.0
    # ADR 0049 (L2): the list price weighs on the purchase at ε, on the click at ε/3.
    on = planted_switches.ON["L2"]
    click *= (price ** (1 / 3) if on else price) * listing.click_odds(state.image_count, state.ad_level)
    price **= merchandising.LIST_PRICE_REACH if on else 1.0
    # Seen on the product page, after the click: they scale cart and purchase, as the odds do. On the last step
    # alone they would barely show, since a relevant product is bought nearly whenever it is carted.
    listed = listing.purchase_given_click_odds(state.image_count, state.description_quality)
    return click, odds * price * quality * listed, purchase_only


def _merchandising_weight(events: catalogue_events.CatalogueEvents, product: Product, state) -> float:
    """How much the shop's ranker favours a product this month: its offer
    (placement), being new or a rival's launch (P2), its stars (R5), the season (S4)."""
    return (merchandising.placement_factor(state) * events.pick_factor(product.sku, state.month)
            * review_chain.rating_pick_factor(state.rating_band) * shoppers.season_factor(product.category, state.month))


def _draw_session(shop: _Shop, life: _Household, rng: random.Random, month: str,
                  index: int) -> tuple[_Session, list[tuple[Product, catalogue_events.ProductState]]]:
    """One session: what it showed, and what it sold (ADR 0045). Returns the
    session and its purchases (the order's lines, in order of showing)."""
    customer, cid = life.customer, life.customer.customer_id
    states = shop.states[month]
    funnel = lambda placement, position: stream(RNG_SEED, "funnel", cid, index, placement, position)
    impressions: list[Impression] = []
    bought: list[tuple[Product, catalogue_events.ProductState]] = []
    just_bought_skus = set(life.prev_skus.split()) if life.prev_skus else set()
    owned_before = set(life.owned_tokens)

    def show(product: Product, placement: str, position: int, clicked: bool, added: bool, purchased: bool) -> None:
        state = states[product.sku]
        impressions.append(Impression(impression_id="", context="", product_sku=product.sku,
                                      product_state=state.product_state_id, position=position,
                                      placement=placement, just_bought=product.sku in just_bought_skus,
                                      clicked=clicked, added_to_cart=added, purchased=purchased))
        if purchased:
            bought.append((product, state))

    # 1. Buy again: what the household came for. Bought with its intent, as odds.
    for position, (product, intent) in enumerate(_buy_again(shop, life, rng, month)):
        _, odds, purchase_only = _price_and_state_odds(shop, customer, product, states[product.sku])
        p = _scale_odds(merchandising.INTENT_P[intent], odds * purchase_only)
        purchased = funnel("buy_again", position).random() < p
        show(product, "buy_again", position, purchased, purchased, purchased)
    basket_rows = [p for p, _ in bought]
    basket = shoppers.basket_tokens(basket_rows)

    # 2. The shop's list, unless the session is a direct reorder.
    query: str | None = None
    if rng.random() < merchandising.DIRECT_P:
        surface = "direct"
    else:
        surface = rng.choices(list(_SURFACE_WEIGHTS), weights=list(_SURFACE_WEIGHTS.values()))[0]
        query = _show_list(shop, life, rng, month, surface, basket, owned_before, just_bought_skus,
                           {imp.product_sku for imp in impressions}, funnel, show)

    # 3. Checkout: dental chews with dog dry food (Signal #2), treat-loving owners more often.
    if customer.segment in ("dog_owner", "multi_pet") and any(
            p.pet_type == "dog" and p.category == "dry-food" for p, _ in bought):
        dental_p = {"high": 0.90, "medium": 0.70, "low": 0.35}[customer.treat_affinity]
        if rng.random() < dental_p:
            shown = {imp.product_sku for imp in impressions}
            dental = [p for p in shop.by_pet_in[month]["dog"] if p.category == "dental-treats" and p.sku not in shown]
            if dental:
                product = rng.choice(dental)
                _, odds, purchase_only = _price_and_state_odds(shop, customer, product, states[product.sku])
                p = _scale_odds(merchandising.INTENT_P["checkout"], odds * purchase_only)
                purchased = funnel("checkout", 0).random() < p
                show(product, "checkout", 0, purchased, purchased, purchased)

    # ADR 0040: where the visit came from; ADR 0038 and pets_from_orders: what
    # the shop can derive from the customer's earlier purchases.
    source = customer.first_source if life.orders == 0 else acquisition.draw_returning_source(life.visit_rng)
    interest = _interest_category(stream(RNG_SEED, "interest", cid, index), life.pet_type_weights, life.cat_bias)
    landing, landing_category = acquisition.draw_landing(stream(RNG_SEED, "landing", cid, index), source, interest)
    before = [st for m, st in life.bought if m < month]
    context = observable.Context(
        context_id="", customer=cid, visitor="", month=month, weekday="", surface=surface, source=source,
        landing=landing, landing_category=landing_category,
        offer_share=observable.share_band("offer", sum(st.on_offer for st in before), len(before)),
        new_share=observable.share_band("new", sum(st.age == "new" for st in before), len(before)),
        label_share=observable.share_band("label", sum(st.label != "none" for st in before), len(before)),
        pets_from_orders=observable.pets_from_orders(pet for m, pet in life.pets_bought if m < month),
        search_query=query,
        basket=" ".join(sorted(p.sku for p in basket_rows)) or None,
        basket_categories=" ".join(basket) or None,
        prev_basket=life.prev_skus,
        owned=" ".join(sorted(owned_before)) or None,
    )
    return _Session(context, impressions, bool(bought)), bought


def _show_list(shop: _Shop, life: _Household, rng: random.Random, month: str, surface: str, basket: list[str],
               owned: set[str], just_bought_skus: set[str], already: set[str], funnel, show) -> str | None:
    """The shop's list for a browsing session: 6–14 products its ranker picked
    and ordered, each with the funnel (ADR 0021) and a click that falls with
    its slot (ADR 0045). Returns the search query, for a search."""
    customer = life.customer
    catalogue = [p for in_category in shop.by_cat_in[month].values() for p in in_category]
    query: str | None = None
    if surface == "search":
        # A phrase from a product this customer is drawn to (S7).
        query = _search_query(life.story_rng, catalogue, shop.phrases_of, life.pet_type_weights, life.cat_bias, customer)
        pool = [p for p in shop.phrases[query] if p.sku in shop.states[month]]
    elif surface == "category":
        # One category the customer leans toward, across pet types.
        cat = _pick_product(rng, {"x": catalogue}, "x", life.cat_bias).category \
            if life.cat_bias else rng.choice(list(shop.by_cat_in[month]))
        pool = list(shop.by_cat_in[month].get(cat, []))
    else:
        pool = list(catalogue)
    pool = [p for p in pool if p.sku not in already] or [p for p in catalogue if p.sku not in already]

    # What a good recommender would surface (65 %) and filler (35 %), each
    # weighted by the shop's merchandising: an offer is shown more.
    merch = [_merchandising_weight(shop.events, p, shop.states[month][p.sku]) for p in pool]
    weights = [w * m for w, m in zip(_browse_weights(pool, customer, life.pet_type_weights, life.cat_bias), merch)]
    filler = [shoppers.browse_weight(p.name, p.pet_type, p.category, customer.diet_rule) * m
              for p, m in zip(pool, merch)]
    n_shown = min(rng.randint(*merchandising.LIST_SIZE), len(pool))
    shown: list[Product] = []
    seen: set[str] = set()
    # "Bought together" shows complements of the basket first (S6).
    if surface == "bought_together" and basket:
        complements = [p for p in pool if shoppers.complements_basket(_product_row(p), basket)]
        for pick in life.story_rng.sample(complements, min(len(complements), n_shown // 2)):
            seen.add(pick.sku)
            shown.append(pick)
    guard = 0
    while len(shown) < n_shown and guard < n_shown * 8:
        guard += 1
        pick = rng.choices(pool, weights=weights if rng.random() < 0.65 else filler, k=1)[0]
        if pick.sku not in seen:
            seen.add(pick.sku)
            shown.append(pick)
    score = {p.sku: w for p, w in zip(pool, weights)}
    ordered = merchandising.list_order(rng, shown, lambda p: score[p.sku])

    for position, product in enumerate(ordered):
        odds = click_odds = 1.0
        if not shoppers.keeps_diet_rule(product.name, product.pet_type, product.category, customer.diet_rule):
            odds = 0.0   # a rule household looks, but never buys it (S1)
        kind = lifecycle.item_type(product.name, product.brand)
        if kind in life.owned_durables:
            odds *= merchandising.OWNED_DURABLE_ODDS      # nobody needs a second cage (D3)
        if shoppers.out_of_order(product.pet_type, kind, life.owned_durables):
            odds *= merchandising.OUT_OF_ORDER_ADD_ON_ODDS
        staple = life.staples.get((product.pet_type, product.category))
        if staple is not None and staple.sku != product.sku:
            odds *= merchandising.OTHER_FOOD_ODDS          # they buy the food they settled on (D1)
        if product.sku in just_bought_skus:
            # Still stocked up (S8): less likely to look, or to buy.
            odds *= shoppers.JUST_BOUGHT_ODDS
            click_odds *= shoppers.JUST_BOUGHT_ODDS
        if basket and shoppers.complements_basket(_product_row(product), basket,
                                                  include_kit=not observable.KIT_PROGRESSION):
            odds *= shoppers.COMPLEMENT_ODDS
            click_odds *= shoppers.COMPLEMENT_ODDS
        if observable.KIT_PROGRESSION:
            # K1: where the household is in its kit, from the basket and what it owns.
            kit = observable.kit_odds(_product_row(product), set(basket), owned)
            odds *= kit
            click_odds *= kit
        state_click, state_odds, purchase_odds = _price_and_state_odds(shop, customer, product,
                                                                       shop.states[month][product.sku])
        click_odds *= merchandising.SHOPPING_CLICK_ODDS * merchandising.position_click_odds(position)
        clicked, added, purchased = _impression_funnel(
            funnel("list", position), product, customer, life.pet_type_weights, life.cat_bias,
            odds * state_odds, click_odds * state_click, purchase_odds)
        show(product, "list", position, clicked, added, purchased)
    return query


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



def backfill_first_orders(customers: list[Customer], orders: list[Order]) -> None:
    """ADR 0040: when each customer joined, their first basket, and whether
    they became a regular: 3 or more orders in their first 6 months, known
    only for customers who joined 6 months before the data ends."""
    by_customer: dict[str, list[Order]] = {}
    for o in orders:
        by_customer.setdefault(o.customer_id, []).append(o)
    last_knowable = _add_months(DEMO_TODAY_YYYYMM, -(acquisition.REGULAR_WINDOW_MONTHS - 1))
    for c in customers:
        own = sorted(by_customer.get(c.customer_id, []), key=lambda o: o.month)
        if not own:
            continue
        c.joined_month = own[0].month
        c.first_basket_categories = own[0].line_categories
        if c.joined_month <= last_knowable:
            window_end = _add_months(c.joined_month, acquisition.REGULAR_WINDOW_MONTHS - 1)
            c.became_regular = sum(o.month <= window_end for o in own) >= acquisition.REGULAR_MIN_ORDERS


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

def _sentiment_for(rating: int) -> str:
    if rating >= 4: return "positive"
    if rating <= 2: return "negative"
    return "neutral"


# ── Customer-months panel + review churn label ─────────────────────


def rate_products(products: list[Product], reviews: list[Review]) -> None:
    """Each product's average stars and band from its reviews (ADR 0030, S5)."""
    stars: dict[str, list[int]] = {}
    for r in reviews:
        stars.setdefault(r.product_sku, []).append(r.rating)
    for p in products:
        ratings = stars.get(p.sku)
        p.avg_rating = round(sum(ratings) / len(ratings), 2) if ratings else None
        p.rating_band = shoppers.rating_band(p.avg_rating)


def backfill_review_churn_label(
    reviews: list[Review],
    customers: list[Customer],
) -> None:
    """Set `review.churn_within_90d` from the churn that followed the review.

    True iff the customer is churned (`customer.churned`) AND the review's
    month is at or after their last order month: they never ordered again.
    Reviews are drawn from experiences only (ADR 0039), so this label reads
    what happened after a review, not what wrote it.

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
    customers: list[Customer],
    orders: list[Order],
    reviews: list[Review],
    nps: list[NpsResponse],
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
      - ADR 0039: the latest NPS group so far, and a negative review in this
        month or the 2 before it, replied to or not

    Volumes: ~3000 customers × ~12 months avg ≈ 35-40k rows.
    """
    rng = stream(RNG_SEED, "visits")
    nps_by_cm: dict[tuple[str, str], NpsResponse] = {}
    for answer in nps:
        nps_by_cm[(answer.customer, answer.month)] = answer     # the month's last answer
    negative_by_cm: dict[tuple[str, str], list[Review]] = {}
    for r in reviews:
        if r.rating <= 2:
            negative_by_cm.setdefault((r.customer_id, r.created_at), []).append(r)
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

        latest_nps: str | None = None
        for i in range(n_months):
            m = _add_months(first_m, i)
            if (c.customer_id, m) in nps_by_cm:
                latest_nps = nps_by_cm[(c.customer_id, m)].nps_group
            negative = [r for k in range(3) for r in negative_by_cm.get((c.customer_id, _add_months(m, -k)), [])]
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
                pets=" ".join(c.pets) if c.pet_profile else None,
                dog_size=c.pet_size if c.pet_profile and "dog" in c.pets else None,
                region=c.region,
                tenure_months_at_month=i,
                latest_rating=review.rating if review is not None else None,
                latest_sentiment=review.sentiment if review is not None else None,
                latest_category=review.category if review is not None else None,
                churned_in_3_months=label,
                nps_latest_group=latest_nps,
                had_negative_review=bool(negative),
                review_replied=any(r.replied for r in negative),
            ))
            cm_counter += 1

    return out


# ── Operate section: monthly_sales + inventory ─────────────────────


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


# Doubling-width ranges: being off by 2 units matters at 3, not at 30.
UNITS_RANGES = ((0, "0"), (1, "1"), (3, "2-3"), (7, "4-7"),
                (15, "8-15"), (31, "16-31"))


def units_range(units: int) -> str:
    """The sales range a unit count falls in: 0, 1, 2-3, 4-7, 8-15, 16-31, 32+."""
    assert units >= 0, f"negative units: {units}"
    for upper, label in UNITS_RANGES:
        if units <= upper:
            return label
    return "32+"


def gen_monthly_sales(
    products: list[Product],
    orders: list[Order],
    lines: list[OrderLine],
    events: catalogue_events.CatalogueEvents,
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

    # Every SKU-month, zero-sale months included (ADR 0027 amendment 3): a
    # demand curve learned without them can't see the months a promotion
    # turned from no sales into some.
    empty = {"units": 0, "revenue": 0.0, "customers": set()}
    out: list[MonthlySale] = []
    for sku, month in sorted((p.sku, m) for p in products for m in _MONTH_WINDOW
                             if events.on_sale(p.sku, m)):
        prod = sku_to_product[sku]
        data = agg.get((sku, month), empty)
        month_int = int(month.split("-")[1])
        units = int(data["units"])
        previous = agg.get((sku, _add_months(month, -1)))
        units_last_month = int(previous["units"]) if previous else 0
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
            units_last_month=units_last_month,
            units_bucket=units_range(units),
            units_last_month_bucket=units_range(units_last_month),
            product_state=f"{sku}-{month}",
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


def backfill_monthly_sales_prices(
    monthly_sales: list[MonthlySale],
    states: list[catalogue_events.ProductState],
) -> None:
    """Overwrite `monthly_sales.price_eur` with the month's realised price
    from its product state, and recompute `revenue_eur = price × units`, so
    `_estimate units_sold` conditions on the price shoppers paid (ADR 0016,
    ADR 0032). `gen_monthly_sales` sets the list price as a placeholder."""
    state_by_id = {st.product_state_id: st for st in states}
    for ms in monthly_sales:
        state = state_by_id[ms.product_state]   # every sales month is a month on sale
        ms.price_eur = state.price_eur
        ms.revenue_eur = _round_eur(state.price_eur * ms.units_sold)
        # ADR 0045: what `_estimate units_sold` can read of the price, in one hop.
        # ADR 0049: the effective price against the product's original list price, so a list price
        # change and an offer both show in it.
        ms.price_index = round(state.price_eur / state.list_price_eur * state.list_price_index, 3)
        ms.discount_band = state.discount_band
        ms.list_price_index = state.list_price_index
        ms.image_count = state.image_count
        ms.description_quality = state.description_quality
        ms.ad_level = state.ad_level
    _backfill_units_index(monthly_sales)


def _relative_to_earlier_months(monthly_sales: list[MonthlySale], column: str) -> list[float | None]:
    """`column` ÷ the product's mean of it in the months before, per row in `monthly_sales`' order: a target a
    regression can read as multiplicative across products (ADR 0049). None in a product's first month, and
    when the earlier months held nothing."""
    by_product: dict[str, list[tuple[str, int]]] = {}
    for i, ms in enumerate(monthly_sales):
        by_product.setdefault(ms.product_sku, []).append((ms.month, i))
    index: list[float | None] = [None] * len(monthly_sales)
    for rows in by_product.values():
        total = 0
        for n, (_, i) in enumerate(sorted(rows)):
            value = getattr(monthly_sales[i], column)
            mean = total / n if n else 0.0
            index[i] = round(value / mean, 3) if mean > 0 else None
            total += value
    return index


def _backfill_units_index(monthly_sales: list[MonthlySale]) -> None:
    """`units_index`: units ÷ the product's mean units in the months before it (ADR 0049)."""
    for ms, value in zip(monthly_sales, _relative_to_earlier_months(monthly_sales, "units_sold")):
        ms.units_index = value


def backfill_showings(monthly_sales: list[MonthlySale], contexts: list[observable.Context],
                      impressions: list[Impression]) -> None:
    """`monthly_sales.showings`: the product's recorded impressions that month
    (consenting shoppers' only, so an observable proxy, ADR 0045)."""
    month_of = {c.context_id: c.month for c in contexts}
    showings = Counter((imp.product_sku, month_of[imp.context]) for imp in impressions)
    for ms in monthly_sales:
        ms.showings = showings[(ms.product_sku, ms.month)]
    # ADR 0050: the funnel's first step, relative to the product's own earlier months.
    for ms, value in zip(monthly_sales, _relative_to_earlier_months(monthly_sales, "showings")):
        ms.showings_index = value


def gen_winback_campaigns(
    rng: random.Random,
    customers: list[Customer],
    products: list[Product],
    orders: list[Order],
    lines: list[OrderLine],
    events: catalogue_events.CatalogueEvents,
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
    # ADR 0027: what each customer actually buys, so a send can hit (or
    # miss) their staple, and the sends concentrate on products that get
    # enough of them to learn from.
    by_sku = {p.sku: p for p in products}
    customer_of = {o.order_id: o.customer_id for o in orders}
    bought: dict[str, Counter] = {}
    for ln in lines:
        prod = by_sku[ln.product_sku]
        bought.setdefault(customer_of[ln.order_id], Counter())[(prod.pet_type, prod.category)] += 1
    popularity = Counter(ln.product_sku for ln in lines)
    universe = [by_sku[sku] for sku, _ in popularity.most_common(200)]

    def staple_of(customer_id: str) -> tuple[str, str] | None:
        counts = bought.get(customer_id)
        if not counts:
            return None
        (pet, category), n = counts.most_common(1)[0]
        return (pet, category) if n >= 3 else None

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
            weights=[0.40, 0.30, 0.15, 0.10, 0.05],
        )[0]
        if n_sends == 0:
            continue

        preferred_pets = segment_to_pets.get(customer.segment, set())
        staple = staple_of(customer.customer_id)
        staple_pool = [p for p in universe if staple and (p.pet_type, p.category) == staple]
        ever_bought = set(bought.get(customer.customer_id, {}))
        for _ in range(n_sends):
            sent_month = rng.choices(months, weights=month_weights)[0]

            # Pick a product to email. Bias slightly toward the
            # customer's preferred pet_type so the engineered
            # "matching products respond better" pattern has enough
            # matched samples to learn from. Off-segment products
            # still occur (failed-campaign realism).
            if staple_pool and rng.random() < 0.5:
                pool = staple_pool
            elif preferred_pets and rng.random() < 0.7:
                pool = [p for p in universe if p.pet_type in preferred_pets]
            else:
                pool = universe
            pool = [p for p in pool if events.on_sale(p.sku, sent_month)]
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
            # ADR 0027: product-level response, relative to what the customer buys.
            if staple and (product.pet_type, product.category) == staple:
                p *= 2.5
            elif (product.pet_type, product.category) not in ever_bought:
                p *= 0.5
            p = max(0.005, min(0.35, p))

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
                customer_staple_category=f"{staple[0]}/{staple[1]}" if staple else "none",
                product_pet_type=product.pet_type,
                product_category=product.category,
                product_brand=product.brand,
                responded=responded,
                order_value_eur=order_value,
            ))
            counter += 1

    return campaigns


# ── Impressions (recommendation KPI) ────────────────────────────────

def _search_query(
    rng: random.Random,
    products: list[Product],
    phrases_of: dict[str, list[str]],
    pet_type_weights: dict[str, float],
    cat_bias: dict[str, float] | None,
    customer: Customer,
) -> str:
    """A search phrase (S7): pick a product this customer is drawn to,
    affinity-weighted as the shown lists are, and search with words from
    its name ("grain free puppy food"). Products whose type is one word
    ("Cage") have no phrase, so the draw is over those that do."""
    candidates = [p for p in products if p.sku in phrases_of]
    weights = [max(pet_type_weights.get(p.pet_type, 0.003)
                   * (0.5 + 5 * (cat_bias.get(p.category, 0.05) if cat_bias else 0.1))
                   * _customer_product_score(p, customer)
                   * shoppers.browse_weight(p.name, p.pet_type, p.category, customer.diet_rule), 1e-4)
               for p in candidates]
    target = rng.choices(candidates, weights=weights, k=1)[0]
    return rng.choice(phrases_of[target.sku])


# How browsing sessions distribute across surfaces.
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

_SURFACE_WEIGHTS: dict[str, float] = {
    "search": 0.40, "for_you": 0.30, "category": 0.20, "bought_together": 0.10,
}


def _impression_funnel(
    rng: random.Random,
    product: Product,
    customer: Customer,
    pet_type_weights: dict[str, float],
    cat_bias: dict[str, float] | None,
    odds: float = 1.0,
    click_odds: float = 1.0,
    purchase_odds: float = 1.0,
    can_buy: bool = True,
) -> tuple[bool, bool, bool]:
    """Draw (clicked, added_to_cart, purchased) for one shown product.

    `odds` scales the add-to-cart and purchase odds: below 1 for a poorly
    made product, above 1 for a complement of the basket. `click_odds`
    scales the click: a complement of the basket draws the eye (ADR 0030).
    `purchase_odds` scales the last step only (low stock, ADR 0038 P10).

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

    Monotone by construction: purchase requires cart requires click. `rng`
    is the impression's own: its three uniforms are drawn whatever happens,
    so a null generation that changes the odds compares the same draws.
    A visitor who hasn't bought yet never buys (`can_buy`, ADR 0040).
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

    click_p = _scale_odds(click_p, click_odds)
    cart_p = _scale_odds(cart_p, odds)
    purchase_p = _scale_odds(purchase_p, odds * purchase_odds)

    u_click, u_cart, u_purchase = rng.random(), rng.random(), rng.random()
    clicked = u_click < click_p
    added = clicked and u_cart < cart_p
    purchased = can_buy and added and u_purchase < purchase_p
    return clicked, added, purchased


def _scale_odds(p: float, odds: float) -> float:
    """`p` with its odds p / (1 − p) multiplied by `odds`."""
    return p * odds / (1 - p + p * odds)


@dataclass
class _ImpressionWorld:
    """What a visitor's landing page reads: this month's catalogue and states, and the search phrases."""
    state_of: dict[tuple[str, str], catalogue_events.ProductState]
    on_sale_in: dict[str, list[Product]]
    by_cat_in: dict[str, dict[str, list[Product]]]
    phrases: dict[str, list[Product]]
    phrases_of: dict[str, list[str]]
    events: catalogue_events.CatalogueEvents
    promotions: lifecycle.Promotions
    contexts: list[observable.Context] = field(default_factory=list)
    impressions: list[Impression] = field(default_factory=list)

    def next_context_id(self) -> str:
        return f"SESS-{len(self.contexts) + 1:06d}"

    def next_impression_id(self) -> str:
        return f"IMP-{len(self.impressions) + 1:07d}"


def gen_impressions(
    customers: list[Customer],
    products: list[Product],
    history: OrderHistory,
    events: catalogue_events.CatalogueEvents,
    promotions: lifecycle.Promotions,
) -> tuple[list[observable.Context], list[Impression]]:
    """Every recorded visit, and the products each showed.

    Customers' sessions come from the order loop (ADR 0045), recorded for
    those who consented (ADR 0044). Visitors who never buy come after, from
    `acquisition.never_buy_sessions`, and visitor ids are assigned to all.
    """
    state_of = {(st.product_sku, st.month): st for st in history.states}
    on_sale_in = {m: [p for p in products if (p.sku, m) in state_of] for m in _MONTH_WINDOW}
    by_cat_in: dict[str, dict[str, list[Product]]] = {}
    for m, on_sale in on_sale_in.items():
        by_cat_in[m] = {}
        for p in on_sale:
            by_cat_in[m].setdefault(p.category, []).append(p)
    phrases = shoppers.query_phrases(products)
    phrases_of: dict[str, list[str]] = {}
    for phrase, matching in phrases.items():
        for p in matching:
            phrases_of.setdefault(p.sku, []).append(phrase)
    world = _ImpressionWorld(state_of, on_sale_in, by_cat_in, phrases, phrases_of, events, promotions,
                             contexts=list(history.contexts), impressions=list(history.impressions))

    visitor_keys: list[tuple[str, int]] = [("customer", i) for i in range(len(customers))]
    first_orders = Counter((c.first_source, c.joined_month) for c in customers if c.joined_month)
    anonymous_from = len(world.contexts)
    for visitor in _never_buy_visits(world, first_orders):
        visitor_keys.append(("anonymous", visitor))
    _assign_visitor_ids(world, customers, visitor_keys, anonymous_from)
    return world.contexts, world.impressions


def _browse_weights(pool: list[Product], shopper: Customer, pet_type_weights: dict[str, float],
                    cat_bias: dict[str, float] | None) -> list[float]:
    """How likely each product is to be shown to this shopper: pet type,
    category, their product score, and their diet rule (S1)."""
    weights = []
    for p in pool:
        pt = pet_type_weights.get(p.pet_type, 0.003)
        cb = cat_bias.get(p.category, 0.05) if cat_bias else 0.1
        weights.append(max(pt * (0.5 + 5 * cb) * _customer_product_score(p, shopper)
                           * shoppers.browse_weight(p.name, p.pet_type, p.category, shopper.diet_rule), 1e-4))
    return weights


def _interest_category(rng: random.Random, pet_type_weights: dict[str, float],
                       cat_bias: dict[str, float] | None) -> str:
    """The category a visit came for: one of the shopper's pets, then a
    category by their bias (ADR 0040's landing category)."""
    pet = rng.choices(list(pet_type_weights), weights=list(pet_type_weights.values()), k=1)[0]
    categories = [c for pt, c in PET_CATEGORY_PAIRS if pt == pet]
    weights = [cat_bias.get(c, 0.05) if cat_bias else 1.0 for c in categories]
    return rng.choices(categories, weights=weights, k=1)[0]


def _product_row(p: Product) -> dict:
    """The products.json-style row the S6 and K1 rules read."""
    return {"pet_type": p.pet_type, "name": p.name, "brand": p.brand, "category": p.category}


def _anonymous_shopper(visitor: int, source: str) -> tuple[Customer, dict[str, float], dict[str, float] | None]:
    """A visitor who never buys still has tastes: a hidden profile drawn as a
    customer's is, kept in memory only."""
    rng = stream(RNG_SEED, "anonymous", visitor)
    segment = rng.choices(SEGMENTS, weights=[SEGMENT_WEIGHTS[s] for s in SEGMENTS])[0]
    pet_size = rng.choices(PET_SIZES, weights=[0.18, 0.42, 0.40])[0] if segment in ("dog_owner", "multi_pet") else None
    lifestyle, health_focus, treat_affinity, brand_loyalty = _sample_customer_traits(rng, segment)
    shopper = Customer(customer_id=f"visitor-{visitor}", name="", segment=segment, pet_size=pet_size,
                       region="", tenure_months=0, lifestyle=lifestyle, health_focus=health_focus,
                       treat_affinity=treat_affinity, brand_loyalty=brand_loyalty,
                       favorite_brands=_pick_favorite_brands(rng, segment, lifestyle, brand_loyalty))
    shopper.sensitivities = sensitivities.draw_sensitivities(rng, lifestyle, health_focus, brand_loyalty, source)
    pet_type_weights = _segment_pet_type_weights(segment, pet_size)
    return shopper, pet_type_weights, _category_bias_for_customer(_category_bias(segment, pet_size), shopper)


def _never_buy_visits(world: _ImpressionWorld, first_orders: Counter) -> list[int]:
    """The visits of visitors who never buy (ADR 0040, F2's denominator).
    Most bounce: a context with no impressions. The rest see a few products
    on the page they landed on. Returns the visitors, in order."""
    visitors: list[int] = []
    session_of: Counter = Counter()
    profiles: dict[int, tuple] = {}
    for source, month, visitor in acquisition.never_buy_sessions(RNG_SEED, first_orders):
        if not person_data.visitor_consents(RNG_SEED, visitor):
            continue   # ADR 0044: a visitor who declined tracking leaves no rows
        if visitor not in profiles:
            profiles[visitor] = _anonymous_shopper(visitor, source)
            visitors.append(visitor)
        shopper, pet_type_weights, cat_bias = profiles[visitor]
        k = session_of[visitor]
        session_of[visitor] += 1
        interest = _interest_category(stream(RNG_SEED, "interest", "visitor", visitor, k), pet_type_weights,
                                      cat_bias)
        landing, landing_category = acquisition.draw_landing(stream(RNG_SEED, "landing", "visitor", visitor, k),
                                                             source, interest)
        rng = stream(RNG_SEED, "landing-page", visitor, k)
        context = observable.Context(
            context_id=world.next_context_id(), customer=None, visitor=f"visitor-{visitor}", month=month,
            weekday="", surface="landing", source=source, landing=landing, landing_category=landing_category)
        context.weekday = random.Random(f"weekday:{context.context_id}").choice(WEEKDAYS)
        world.contexts.append(context)
        if rng.random() < acquisition.BOUNCE_P:
            continue
        pool = _landing_pool(world, rng, month, landing, landing_category, shopper, pet_type_weights, cat_bias)
        n_shown = min(rng.randint(*acquisition.LANDING_PAGE_PRODUCTS), len(pool))
        weights = [w * _merchandising_weight(world.events, p, world.state_of[(p.sku, month)])
                   for p, w in zip(pool, _browse_weights(pool, shopper, pet_type_weights, cat_bias))]
        shown: list[Product] = []
        while len(shown) < n_shown:
            pick = rng.choices(pool, weights=weights, k=1)[0]
            if pick not in shown:
                shown.append(pick)
        score = {p.sku: w for p, w in zip(pool, weights)}
        for position, product in enumerate(merchandising.list_order(rng, shown, lambda p: score[p.sku])):
            state = world.state_of[(product.sku, month)]
            state_click, state_odds, purchase_odds = _price_and_state_odds(world, shopper, product, state)
            clicked, added, purchased = _impression_funnel(
                stream(RNG_SEED, "funnel", "visitor", visitor, k, position), product, shopper,
                pet_type_weights, cat_bias, state_odds, state_click * merchandising.position_click_odds(position),
                purchase_odds, can_buy=False)
            world.impressions.append(Impression(
                impression_id=world.next_impression_id(), context=context.context_id,
                product_sku=product.sku, product_state=state.product_state_id, position=position,
                clicked=clicked, added_to_cart=added, purchased=purchased))
    return visitors


def _landing_pool(world: _ImpressionWorld, rng: random.Random, month: str, landing: str,
                  landing_category: str | None, shopper: Customer, pet_type_weights: dict[str, float],
                  cat_bias: dict[str, float] | None) -> list[Product]:
    """The products a landing page can show."""
    catalogue = world.on_sale_in[month]
    if landing == "search":
        query = _search_query(rng, catalogue, world.phrases_of, pet_type_weights, cat_bias, shopper)
        pool = [p for p in world.phrases[query] if (p.sku, month) in world.state_of]
    elif landing == "offer":
        pool = [p for p in world.by_cat_in[month].get(landing_category, catalogue)
                if world.state_of[(p.sku, month)].on_offer]
    elif landing in ("product", "category"):
        pool = list(world.by_cat_in[month].get(landing_category, []))
    else:
        pool = list(catalogue)
    return pool or list(catalogue)


def _assign_visitor_ids(world: _ImpressionWorld, customers: list[Customer],
                        visitor_keys: list[tuple[str, int]], anonymous_from: int) -> None:
    """Visitor ids in a shuffled order, so an id says nothing about whether
    the visitor became a customer."""
    order = list(range(len(visitor_keys)))
    stream(RNG_SEED, "visitor-ids").shuffle(order)
    vis_id = {key: f"VIS-{order[i] + 1:07d}" for i, key in enumerate(visitor_keys)}
    customer_index = {c.customer_id: i for i, c in enumerate(customers)}
    for c in customers:
        c.visitor = vis_id[("customer", customer_index[c.customer_id])]
    for context in world.contexts[:anonymous_from]:
        # Set to the customer's id when numbered: before a first order the context has no customer.
        context.visitor = vis_id[("customer", customer_index[context.visitor])]
    for context in world.contexts[anonymous_from:]:
        context.visitor = vis_id[("anonymous", int(context.visitor.removeprefix("visitor-")))]


# ── Output ──────────────────────────────────────────────────────────

def _to_json_dict(obj) -> dict:
    """Strip None values from output. Aito treats absent and null-typed
    differently for nullable columns — we send absent for nulls.

    Also drops the in-memory-only `favorite_brands` field from
    `Customer` — it powers the order-generation loop but isn't part
    of the public dataset (and isn't a meaningful column for Aito's
    inference machinery — it's a derived view of brand_loyalty).
    """
    if isinstance(obj, dict):
        return {k: v for k, v in obj.items() if v is not None}
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
    assign_sources_and_sensitivities(customers)
    # ADR 0027: promotions are decided before any order, on their own
    # RNG, so demand can respond to price rather than price to demand.
    promotions = lifecycle.plan_promotions(random.Random(RNG_SEED + 27), products, _MONTH_WINDOW)
    # ADR 0032: launches and price rises, decided before any order too.
    events = catalogue_events.plan_catalogue_events(random.Random(RNG_SEED + 32), products, _MONTH_WINDOW,
                                                    promotions.mispriced)
    # ADR 0039: orders month by month, with what each led to: experiences,
    # reviews (whose stars the next month's orders see), NPS answers, churn.
    # ADR 0044: consent decides what is recorded of the sessions below.
    person_data.assign_consent(RNG_SEED, customers, always_consenting={p.customer_id for p in PERSONAS})
    # ADR 0045: every sale is a purchase in a session, month by month, with what
    # each order led to (ADR 0039): experiences, reviews, NPS answers, churn.
    history = gen_orders_and_lines(customers, products, promotions, events)
    orders, lines, reviews = history.orders, history.lines, history.reviews

    # Post-pass: derive customer-level aggregates from the order
    # history (total_orders, total_spent_eur, last_order_month,
    # churned). Powers the Churn view's `_predict` features.
    backfill_customer_aggregates(customers, orders)
    backfill_first_orders(customers, orders)
    # ADR 0044: what each person told the shop, and whether they consented to
    # behavioural tracking. After the orders: the diet rule is drawn there.
    person_data.assign(RNG_SEED, customers, always_with_profile={p.customer_id for p in PERSONAS})
    rate_products(products, reviews)
    # Forward-looking churn label per review, from the churn that followed it.
    backfill_review_churn_label(reviews, customers)

    # Customer-month panel — the training shape for time-series churn
    # prediction. Drives the Churn view's at-risk leaderboard + the
    # `_evaluate` accuracy band. See ADR 0013.
    customer_months = gen_customer_months(customers, orders, reviews, history.nps)

    # Operate-section tables: SKU × month sales aggregate (drives the
    # Demand Forecast view + feeds Inventory's daily-demand), per-SKU
    # stock snapshot (Inventory's reorder workflow). See ADRs 0014 / 0015.
    # ADR 0045: monthly_sales is the sum of purchased order lines.
    monthly_sales = gen_monthly_sales(products, orders, lines, events)
    inventory = gen_inventory(rng, products, monthly_sales)
    # Each product as it was each month on sale, drawn at the month's start in
    # the session loop (ADR 0032, ADR 0038, ADR 0045).
    product_states = history.states
    backfill_monthly_sales_prices(monthly_sales, product_states)
    # Historical re-engagement campaigns — drives the Win-back
    # view's `_predict responded` per current-churned customer.
    # See ADR 0020.
    winback_campaigns = gen_winback_campaigns(rng, customers, products, orders, lines, events)
    # ADR 0051: what the shop did for a customer, and what followed in 30 days.
    customer_actions = customer_actions_module.gen_customer_actions(
        RNG_SEED, customers, orders, lines, product_states, history.nps, winback_campaigns,
        _MONTH_WINDOW, {p.customer_id for p in PERSONAS})
    action_contexts = customer_actions_module.gen_action_contexts(
        customers, orders, lines, product_states, history.nps, winback_campaigns, _MONTH_WINDOW)

    # Visits, and the products they showed with the funnel outcome: the
    # recommendation surfaces' conversion KPI (`_recommend goal:
    # {purchased: true}`, ADR 0021), and ADR 0040's never-buy visitors.
    contexts, impressions = gen_impressions(customers, products, history, events, promotions)
    backfill_showings(monthly_sales, contexts, impressions)

    write_json(DATA_DIR / "products.json", products)
    # ADR 0033: what a shop has; the hidden traits stay in the generator.
    write_json(DATA_DIR / "customers.json", [observable.public_customer(c) for c in customers])
    write_json(DATA_DIR / "orders.json", orders)
    write_json(DATA_DIR / "order_lines.json", lines)
    write_json(DATA_DIR / "reviews.json", reviews)
    write_json(DATA_DIR / "nps_responses.json", history.nps)
    write_json(DATA_DIR / "customer_months.json", customer_months)
    write_json(DATA_DIR / "monthly_sales.json", monthly_sales)
    write_json(DATA_DIR / "inventory.json", inventory)
    write_json(DATA_DIR / "product_states.json", product_states)
    write_json(DATA_DIR / "winback_campaigns.json", winback_campaigns)
    write_json(DATA_DIR / "customer_actions.json", customer_actions)
    write_json(DATA_DIR / "action_contexts.json", action_contexts)
    write_json(DATA_DIR / "contexts.json", contexts)
    # The generator's answer key, for the data checks; Aito never sees it.
    answer_key = DATA_DIR / "answer_key"
    answer_key.mkdir(exist_ok=True)
    write_json(answer_key / "customer_traits.json", [observable.answer_key_row(c) for c in customers])
    write_json(answer_key / "product_quality.json",
               [{"sku": p.sku, "quality": review_chain.quality(p.sku)} for p in products])
    write_json(answer_key / "line_experiences.json",
               [{"line_id": line_id, "experience": e} for line_id, e in history.experience_of.items()])
    write_json(DATA_DIR / "impressions.json", impressions)

    # ── Summary print ───────────────────────────────────────────────
    print(f"  products        {len(products):>6}")
    print(f"  customers       {len(customers):>6}")
    print(f"  orders          {len(orders):>6}")
    print(f"  order_lines     {len(lines):>6}")
    print(f"  reviews         {len(reviews):>6}")
    print(f"  nps_responses   {len(history.nps):>6}")
    print(f"  customer_months {len(customer_months):>6}")
    print(f"  monthly_sales   {len(monthly_sales):>6}")
    print(f"  inventory       {len(inventory):>6}")
    print(f"  winback         {len(winback_campaigns):>6}")
    print(f"  customer_actions{len(customer_actions):>6}")
    print(f"  action_contexts {len(action_contexts):>6}")
    print(f"  product_states  {len(product_states):>6}")
    print(f"  contexts        {len(contexts):>6}  ({sum(c.customer is None for c in contexts)} before a first order)")
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
