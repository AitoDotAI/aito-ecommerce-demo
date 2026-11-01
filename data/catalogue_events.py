"""What happens to the catalogue over time, and each product's state per month (ADR 0032).

The planted effects, checked by `tests/test_product_states_data.py` and
`./do planted-effects` against `docs/verification/product-states-prereg.md`:

  P2  Launches: 50 products appear mid-window; new, they are picked more
      and take share from their rivals.
  P3  Price rises: 60 products get one list-price rise; demand follows
      the product's elasticity.
  P5  A dog's size steers the pack size of its food.

How a state moves an impression (an offer, the stars, being new, a label,
low stock) depends on the shopper's hidden sensitivities since ADR 0038:
`data/sensitivities.py`. A state's label and stock come from
`data/shop_levers.py`.

Everything here is decided from its own seeded RNG, before any order, so
orders respond to the catalogue rather than the other way round.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass

from data import incidents as incidents_module
from data import listing as listing_plan
from data.planted_switches import stream
from data.shop_levers import review_count_band

N_LAUNCHES = 50
LAUNCH_WINDOW = ("2024-11", "2026-01")
LAUNCH_CATEGORIES = frozenset({"dry-food", "wet-food", "treats", "dental-treats", "toys", "accessories"})
NEW_MONTHS = 3               # a product is "new" for its first 3 months on sale
LAUNCH_PICK_FACTOR = 2.0     # how much more often a new product is picked in orders
RIVAL_PICK_FACTOR = 0.75     # how much less often its rivals are, for RECENT_MONTHS after
# A household reconsiders its staple after a price rise or a rival's launch:
# its switch probability is this much higher for RECENT_MONTHS. Two
# constants so each effect's null can switch off its own half.
RECONSIDER_AFTER_RISE = 3.0
RECONSIDER_AFTER_RIVAL = 3.0
SWITCH_TO_RIVAL = True       # one who reconsiders because of a rival switches to it
N_RISES = 60
RISE_WINDOW = ("2024-11", "2026-01")
RISE_RANGE = (1.08, 1.15)
RECENT_MONTHS = 3            # `rival_launched` and `price_change: rise` look back this far

# The products the demo's views, scripts and checks name: they keep their
# whole history and price, so the stories told about them stay true.
DEMO_ANCHORS = frozenset({
    "SKU-PT-0001", "SKU-PT-0012", "SKU-PT-0035", "SKU-PT-0038", "SKU-PT-0042", "SKU-PT-0049",
    "SKU-PT-0133", "SKU-PT-0177", "SKU-PT-0182", "SKU-PT-0206", "SKU-PT-0238", "SKU-PT-0278",
    "SKU-PT-0407", "SKU-PT-0483", "SKU-PT-0530", "SKU-PT-0545", "SKU-PT-0553", "SKU-PT-0555",
    "SKU-PT-0609", "SKU-PT-0611",
})

OFFER_MIN_PCT = 10.0         # below this, a discount is list-price noise, not an offer
PACK_FIT = 2.5                                                               # P5
LARGE_PACK_KG = 7.0
SMALL_PACK_KG = 2.0


@dataclass(frozen=True)
class CatalogueEvents:
    launch_month: dict[str, str]            # sku → its first month on sale
    rise: dict[str, tuple[str, float]]      # sku → (month of the rise, factor)
    original_list: dict[str, float]         # sku → list price before any rise
    slice_of: dict[str, tuple[str, str]]    # sku → (pet_type, category)
    # ((pet_type, category), month) → the products launched in it in the last 3 months.
    recent_launches: dict[tuple[tuple[str, str], str], frozenset[str]]
    listing: listing_plan.Listing | None = None     # ADR 0049: list price policy, pictures, description, ads
    incidents: tuple = ()                           # ADR 0056: planted incidents (data/incidents.py)

    def on_sale(self, sku: str, month: str) -> bool:
        return month >= self.launch_month.get(sku, "") and not incidents_module.withdrawn(self.incidents, sku, month)

    def is_new(self, sku: str, month: str) -> bool:
        launch = self.launch_month.get(sku)
        return launch is not None and launch <= month < add_months(launch, NEW_MONTHS)

    def list_price(self, sku: str, month: str) -> float:
        rise = self.rise.get(sku)
        index = self.listing.list_index.get((sku, month), 1.0) if self.listing else 1.0
        if rise is not None and month >= rise[0]:
            return round(self.original_list[sku] * rise[1] * index, 2)
        return round(self.original_list[sku] * index, 2)

    def raised_since(self, sku: str, month: str) -> float:
        """The list price this month ÷ the original: 1.0 before any rise."""
        return self.list_price(sku, month) / self.original_list[sku]

    def recently_raised(self, sku: str, month: str) -> bool:
        rise = self.rise.get(sku)
        return rise is not None and rise[0] <= month < add_months(rise[0], RECENT_MONTHS)

    def rival_launched(self, sku: str, month: str) -> bool:
        """Another product of the same pet and category launched in the last 3 months."""
        return bool(self.recent_launches.get((self.slice_of[sku], month), frozenset()) - {sku})

    def reconsider_factor(self, sku: str, month: str) -> float:
        """How much likelier a household is to switch away from this staple now."""
        factor = 1.0
        # The price-rise null keeps the planned rise (×1.0) marked; it isn't a rise to react to.
        if self.recently_raised(sku, month) and self.rise[sku][1] > 1.0:
            factor *= RECONSIDER_AFTER_RISE
        if self.rival_launched(sku, month):
            factor *= RECONSIDER_AFTER_RIVAL
        return factor

    def rivals(self, sku: str, month: str) -> list[str]:
        """The products of its pet and category launched in the last 3 months."""
        return sorted(self.recent_launches.get((self.slice_of[sku], month), frozenset()) - {sku})

    def pick_factor(self, sku: str, month: str) -> float:
        """How much more (or less) often an order picks this product this month,
        besides price: a new product pulls (P2), and takes share from its rivals."""
        if self.is_new(sku, month):
            return LAUNCH_PICK_FACTOR
        base = RIVAL_PICK_FACTOR if self.rival_launched(sku, month) else 1.0
        return base * incidents_module.pick_factor(self.incidents, sku, month)


def plan_catalogue_events(rng: random.Random, products: list, months: list[str],
                          mispriced: frozenset[str]) -> CatalogueEvents:
    """Pick the launches and the price rises. A raised product's
    `price_eur` becomes its list price after the rise: the current one."""
    launch_window = [m for m in months if LAUNCH_WINDOW[0] <= m <= LAUNCH_WINDOW[1]]
    launchable = sorted((p for p in products
                         if p.pet_type in ("dog", "cat") and p.category in LAUNCH_CATEGORIES
                         and p.sku not in DEMO_ANCHORS),
                        key=lambda p: p.sku)
    launch_month = {p.sku: rng.choice(launch_window) for p in rng.sample(launchable, N_LAUNCHES)}

    rise_window = [m for m in months if RISE_WINDOW[0] <= m <= RISE_WINDOW[1]]
    raisable = sorted((p for p in products if p.sku not in launch_month and p.sku not in mispriced
                       and p.sku not in DEMO_ANCHORS),
                      key=lambda p: p.sku)
    rise = {p.sku: (rng.choice(rise_window), rng.uniform(*RISE_RANGE)) for p in rng.sample(raisable, N_RISES)}

    original_list = {p.sku: p.price_eur for p in products}
    slice_of = {p.sku: (p.pet_type, p.category) for p in products}
    recent: dict[tuple[tuple[str, str], str], set[str]] = {}
    for sku, launch in launch_month.items():
        for i in range(RECENT_MONTHS):
            recent.setdefault((slice_of[sku], add_months(launch, i)), set()).add(sku)
    # ADR 0049: the listing, last so it draws nothing the older events drew.
    held = frozenset(rise) | mispriced | DEMO_ANCHORS
    planned = listing_plan.plan_listing(rng.randrange(2 ** 32), [p.sku for p in products], months, held)
    events = CatalogueEvents(launch_month, rise, original_list, slice_of,
                             {key: frozenset(skus) for key, skus in recent.items()}, planned)
    for p in products:
        p.price_eur = events.list_price(p.sku, months[-1])
    return events


def add_months(yyyymm: str, n: int) -> str:
    y, m = (int(x) for x in yyyymm.split("-"))
    ny, nm = divmod(y * 12 + (m - 1) + n, 12)
    return f"{ny:04d}-{nm + 1:02d}"


def pack_kg(name: str) -> float | None:
    """"Eukanuba Lamb Dog Food 15kg" → 15.0; "… 400g" → 0.4."""
    match = re.search(r"(\d+(?:\.\d+)?)\s*(kg|g)\b", name)
    if match is None:
        return None
    return float(match.group(1)) * (1.0 if match.group(2) == "kg" else 0.001)


def pack_fit(product, pet_size: str | None) -> float:
    """P5: a large dog's household buys big bags, a small dog's small ones."""
    if product.pet_type != "dog" or product.category not in ("dry-food", "wet-food"):
        return 1.0
    kg = pack_kg(product.name)
    if kg is None:
        return 1.0
    if pet_size == "large" and kg >= LARGE_PACK_KG:
        return PACK_FIT
    if pet_size == "small" and kg <= SMALL_PACK_KG:
        return PACK_FIT
    return 1.0


def discount_band(discount_pct: float) -> str:
    if discount_pct < OFFER_MIN_PCT:
        return "none"
    if discount_pct < 15:
        return "10-15"
    return "15-20" if discount_pct < 20 else "20+"


LIST_PRICE_STEP_PCT = 5


def list_price_band(list_price_index: float) -> str:
    """The list price as a percentage of the original list, to the nearest 5: "85" ... "115".
    The listing draws prices from these price points, so a band is what `_predict` can condition on:
    a decimal index only matches a row whose cents are the same."""
    return str(round(list_price_index * 100 / LIST_PRICE_STEP_PCT) * LIST_PRICE_STEP_PCT)


@dataclass
class ProductState:
    """One product as it was in one month: what a shopper saw (ADR 0032).
    Replaces `price_history`, keeping its id and price columns."""
    product_state_id: str      # "SKU-PT-0001-2025-03"
    product_sku: str           # link → products.sku
    month: str
    price_eur: float
    list_price_eur: float      # the list price that month (after any rise)
    discount_pct: float        # (list_price - price) / list_price × 100
    on_offer: bool             # discount_pct ≥ OFFER_MIN_PCT
    discount_band: str         # "none", "10-15", "15-20", "20+"
    rating_band: str           # from reviews created before the month; "unrated" if none
    age: str                   # "new" (first NEW_MONTHS on sale), "established"
    rival_launched: bool       # a product of the same pet and category launched in the last 3 months
    price_change: str          # "rise" (list price raised in the last 3 months), "none"
    list_price_index: float    # ADR 0049: the list price ÷ the original list, apart from the offer
    list_price_band: str       # that index in percent to the nearest 5: "85" ... "115"
    # ADR 0038: what the shop set or lived with this month.
    label: str                 # "none", "recommended", "staff_pick", "popular"
    stock: str                 # "in_stock", "low"
    review_count_band: str     # "none", "1-4", "5-19", "20+": reviews created before the month
    # ADR 0049: how the shop lists the product.
    image_count: str           # "0-1", "2-3", "4+"
    description_quality: str   # "thin", "ok", "rich"
    ad_level: str              # "none", "search", "banner"


def states_for_month(seed: int, month: str, products: list, events: CatalogueEvents,
                     discount: dict[tuple[str, str], float], stars: dict[str, tuple[str, int]],
                     labels: dict[str, str], low_stock: set[str]) -> list[ProductState]:
    """Every product on sale in `month`, as a shopper sees it at the month's
    start (ADR 0045: the month's sales follow from it). `stars` maps a SKU to
    (rating band, review count) from reviews written before the month. A ±2 %
    noise on the price keeps Aito's k-NN from reading a crisp ridge (ADR 0027)."""
    out = []
    for p in products:
        if not events.on_sale(p.sku, month):
            continue
        list_price = events.list_price(p.sku, month)
        noise = stream(seed, "price-noise", p.sku, month).uniform(-0.02, 0.02)
        listing = events.listing
        offer = max(discount.get((p.sku, month), 0.0), listing.extra_discount.get((p.sku, month), 0.0))
        ratio = (1.0 - offer) * (1.0 + noise)
        discount_pct = round((1.0 - ratio) * 100, 1)
        band, n_reviews = stars.get(p.sku, ("unrated", 0))
        out.append(ProductState(
            product_state_id=f"{p.sku}-{month}",
            product_sku=p.sku,
            month=month,
            price_eur=round(list_price * ratio, 2),
            list_price_eur=list_price,
            discount_pct=discount_pct,
            on_offer=discount_pct >= OFFER_MIN_PCT,
            discount_band=discount_band(discount_pct),
            rating_band=band,
            age="new" if events.is_new(p.sku, month) else "established",
            rival_launched=events.rival_launched(p.sku, month),
            price_change="rise" if events.recently_raised(p.sku, month) else "none",
            label=labels.get(p.sku, "none"),
            stock="low" if p.sku in low_stock else "in_stock",
            review_count_band=review_count_band(n_reviews),
            list_price_index=round(list_price / events.original_list[p.sku], 3),
            list_price_band=list_price_band(list_price / events.original_list[p.sku]),
            image_count=listing.image_count[(p.sku, month)],
            description_quality=listing.description_quality[(p.sku, month)],
            ad_level=listing.ad_level[(p.sku, month)],
        ))
    return out
