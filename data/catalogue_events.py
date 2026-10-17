"""What happens to the catalogue over time, and each product's state per month (ADR 0032).

The planted effects, checked by `tests/test_product_states_data.py`
against `docs/verification/product-states-prereg.md`:

  P1  An offer converts an impression, most for budget shoppers.
  P2  Launches: 50 products appear mid-window; new, they are picked more,
      and flexible shoppers take to them.
  P3  Price rises: 60 products get one list-price rise; demand follows
      the product's elasticity.
  P4  Stars sell: an impression converts by the stars shown that month.
  P5  A dog's size steers the pack size of its food.

Everything here is decided from its own seeded RNG, before any order, so
orders respond to the catalogue rather than the other way round.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass

from data import shoppers

N_LAUNCHES = 50
LAUNCH_WINDOW = ("2024-11", "2026-01")
LAUNCH_CATEGORIES = frozenset({"dry-food", "wet-food", "treats", "dental-treats", "toys", "accessories"})
NEW_MONTHS = 3               # a product is "new" for its first 3 months on sale
LAUNCH_PICK_FACTOR = 2.0     # how much more often a new product is picked in orders
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
OFFER_ODDS = {"budget": 2.5, "mid": 1.8, "premium": 1.2}                     # P1
NEW_ODDS = {"flexible": 1.6, "loyal": 1.0}                                   # P2
STARS_ODDS = {"5": 1.3, "4": 1.15, "3": 1.0, "1-2": 0.8, "unrated": 0.9}     # P4
PACK_FIT = 2.5                                                               # P5
LARGE_PACK_KG = 7.0
SMALL_PACK_KG = 2.0


@dataclass(frozen=True)
class CatalogueEvents:
    launch_month: dict[str, str]            # sku → its first month on sale
    rise: dict[str, tuple[str, float]]      # sku → (month of the rise, factor)
    original_list: dict[str, float]         # sku → list price before any rise
    slice_of: dict[str, tuple[str, str]]    # sku → (pet_type, category)

    def on_sale(self, sku: str, month: str) -> bool:
        return month >= self.launch_month.get(sku, "")

    def is_new(self, sku: str, month: str) -> bool:
        launch = self.launch_month.get(sku)
        return launch is not None and launch <= month < add_months(launch, NEW_MONTHS)

    def list_price(self, sku: str, month: str) -> float:
        rise = self.rise.get(sku)
        if rise is not None and month >= rise[0]:
            return round(self.original_list[sku] * rise[1], 2)
        return self.original_list[sku]

    def raised_since(self, sku: str, month: str) -> float:
        """The list price this month ÷ the original: 1.0 before any rise."""
        return self.list_price(sku, month) / self.original_list[sku]

    def recently_raised(self, sku: str, month: str) -> bool:
        rise = self.rise.get(sku)
        return rise is not None and rise[0] <= month < add_months(rise[0], RECENT_MONTHS)

    def rival_launched(self, sku: str, month: str) -> bool:
        """Another product of the same pet and category launched in the last 3 months."""
        return any(other != sku and self.slice_of[other] == self.slice_of[sku]
                   and launch <= month < add_months(launch, RECENT_MONTHS)
                   for other, launch in self.launch_month.items())

    def pick_factor(self, sku: str, month: str) -> float:
        """How much more often an order picks this product this month, besides price."""
        return LAUNCH_PICK_FACTOR if self.is_new(sku, month) else 1.0


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
    events = CatalogueEvents(launch_month, rise, original_list,
                             {p.sku: (p.pet_type, p.category) for p in products})
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


def ratings_by_month(reviews: list, months: list[str]) -> dict[tuple[str, str], str]:
    """(sku, month) → the rating band its reviews created before the month give."""
    by_sku: dict[str, list] = {}
    for r in reviews:
        by_sku.setdefault(r.product_sku, []).append(r)
    bands: dict[tuple[str, str], str] = {}
    for sku, rows in by_sku.items():
        for month in months:
            earlier = [r.rating for r in rows if r.created_at < month]
            if earlier:
                bands[(sku, month)] = shoppers.rating_band(sum(earlier) / len(earlier))
    return bands


def impression_odds(state, customer) -> tuple[float, float]:
    """(conversion odds, click odds) the product's state gives this shopper: P1, P2, P4."""
    odds = click_odds = 1.0
    if state.on_offer:
        odds *= OFFER_ODDS[customer.lifestyle]
        click_odds *= OFFER_ODDS[customer.lifestyle]
    if state.age == "new":
        odds *= NEW_ODDS[customer.brand_loyalty]
        click_odds *= NEW_ODDS[customer.brand_loyalty]
    odds *= STARS_ODDS[state.rating_band]
    return odds, click_odds


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


def gen_product_states(rng: random.Random, products: list, months: list[str], events: CatalogueEvents,
                       discount: dict[tuple[str, str], float],
                       ratings: dict[tuple[str, str], str]) -> list[ProductState]:
    """Every product in every month it is on sale. A ±2 % noise on the
    price keeps Aito's k-NN from reading a crisp ridge (ADR 0027)."""
    out = []
    for p in products:
        for month in months:
            if not events.on_sale(p.sku, month):
                continue
            list_price = events.list_price(p.sku, month)
            ratio = (1.0 - discount.get((p.sku, month), 0.0)) * (1.0 + rng.uniform(-0.02, 0.02))
            discount_pct = round((1.0 - ratio) * 100, 1)
            out.append(ProductState(
                product_state_id=f"{p.sku}-{month}",
                product_sku=p.sku,
                month=month,
                price_eur=round(list_price * ratio, 2),
                list_price_eur=list_price,
                discount_pct=discount_pct,
                on_offer=discount_pct >= OFFER_MIN_PCT,
                discount_band=discount_band(discount_pct),
                rating_band=ratings.get((p.sku, month), "unrated"),
                age="new" if events.is_new(p.sku, month) else "established",
                rival_launched=events.rival_launched(p.sku, month),
                price_change="rise" if events.recently_raised(p.sku, month) else "none",
            ))
    return out
