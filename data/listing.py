"""The shop's own levers on a product's listing (ADR 0049, 0050): how it is priced, pictured, described and advertised.

Everything is decided before any order, from a seeded stream of its own per product, so orders respond to the
listing and not the other way round, and switching one effect off leaves every other draw where it was
(`planted_switches`). The planted effects (docs/verification/release3a-prereg.md):

  L1  list price moves: `dynamic` products change their list price, `promote` products run extra offers
  L2  the list price's elasticity acts on cart and purchase at ε, and on the click at ε/3
  L3  an offer lifts the click less than the purchase (data/sensitivities.py)
  L4  pictures: more of them, more clicks and more purchases per click
  L5  description: a rich one lifts the purchase per click, not the click
  L6  advertising: more showings and clicks, no more purchases per click
"""

from __future__ import annotations

from dataclasses import dataclass

from data.planted_switches import ON, stream

# Of the products not held anyway (rises, mispriced, demo anchors: about 14 % of all).
POLICIES = (("hold", 0.15), ("dynamic", 0.50), ("promote", 0.35))
LIST_INDEX_STEPS = (0.85, 0.90, 0.95, 1.00, 1.05, 1.10)
STAY_P = 0.4                    # a dynamic product keeps last month's list price with this probability
PROMOTE_OFFER_P = 0.25          # a promote product runs an extra offer in this share of months
PROMOTE_DEPTH = (0.10, 0.25)

IMAGE_LEVELS = ("0-1", "2-3", "4+")
IMAGE_SHARES = (0.25, 0.50, 0.25)
IMAGE_UPGRADE_SHARE = 0.25      # of products add pictures once in the window
DESCRIPTION_LEVELS = ("thin", "ok", "rich")
DESCRIPTION_SHARES = (0.25, 0.55, 0.20)
DESCRIPTION_UPGRADE_SHARE = 0.20
AD_LEVELS = ("none", "search", "banner")
CAMPAIGN_SHARE = 0.15           # of products run one campaign in the window
CAMPAIGN_MONTHS = (1, 3)
BANNER_SHARE = 0.30             # of campaigns

IMAGE_CLICK_ODDS = {"0-1": 0.85, "2-3": 1.0, "4+": 1.15}                          # L4
IMAGE_PURCHASE_ODDS = {"0-1": 0.9, "2-3": 1.0, "4+": 1.15}
DESCRIPTION_PURCHASE_ODDS = {"thin": 0.85, "ok": 1.0, "rich": 1.2}                # L5
AD_PLACEMENT = {"none": 1.0, "search": 1.4, "banner": 1.8}                        # L6
AD_CLICK_ODDS = {"none": 1.0, "search": 1.1, "banner": 1.2}


@dataclass(frozen=True)
class Listing:
    policy: dict[str, str]                          # sku → hold | dynamic | promote
    list_index: dict[tuple[str, str], float]        # (sku, month) → list price ÷ original, dynamic products only
    extra_discount: dict[tuple[str, str], float]    # (sku, month) → an offer a promote product runs on top
    image_count: dict[tuple[str, str], str]
    description_quality: dict[tuple[str, str], str]
    ad_level: dict[tuple[str, str], str]


def plan_listing(seed: int, skus: list[str], months: list[str], held: frozenset[str]) -> Listing:
    """`held` (rises, mispriced, demo anchors) keep their list price and never run extra offers."""
    policy, list_index, extra = {}, {}, {}
    images, descriptions, ads = {}, {}, {}
    for sku in skus:
        policy[sku] = "hold" if sku in held else _pick(stream(seed, "listing-policy", sku).random(), POLICIES)
        if policy[sku] == "dynamic" and ON["L1"]:
            rng, index = stream(seed, "list-index", sku), 1.0
            for month in months:
                if rng.random() >= STAY_P:
                    index = rng.choice(LIST_INDEX_STEPS)
                list_index[(sku, month)] = index
        if policy[sku] == "promote" and ON["L1"]:
            rng = stream(seed, "extra-offer", sku)
            for month in months:
                if rng.random() < PROMOTE_OFFER_P:
                    extra[(sku, month)] = rng.uniform(*PROMOTE_DEPTH)
        _upgrading(stream(seed, "images", sku), sku, months, IMAGE_LEVELS, IMAGE_SHARES, IMAGE_UPGRADE_SHARE, images)
        _upgrading(stream(seed, "description", sku), sku, months, DESCRIPTION_LEVELS, DESCRIPTION_SHARES,
                   DESCRIPTION_UPGRADE_SHARE, descriptions)
        _campaign(stream(seed, "ads", sku), sku, months, ads)
    return Listing(policy, list_index, extra, images, descriptions, ads)


def _pick(u: float, shares: tuple) -> str:
    total = 0.0
    for name, share in shares:
        total += share
        if u < total:
            return name
    return shares[-1][0]


def _upgrading(rng, sku: str, months: list[str], levels: tuple, shares: tuple, upgrade_share: float, out: dict) -> None:
    """A level drawn once, and in `upgrade_share` of products raised one step from a month on."""
    level = _pick(rng.random(), tuple(zip(levels, shares)))
    upgrade_from = rng.choice(months) if rng.random() < upgrade_share else None
    for month in months:
        i = levels.index(level) + (1 if upgrade_from is not None and month >= upgrade_from else 0)
        out[(sku, month)] = levels[min(i, len(levels) - 1)]


def _campaign(rng, sku: str, months: list[str], out: dict) -> None:
    runs = rng.random() < CAMPAIGN_SHARE
    level = "banner" if rng.random() < BANNER_SHARE else "search"
    first = rng.randrange(len(months))
    length = rng.randint(*CAMPAIGN_MONTHS)
    for i, month in enumerate(months):
        out[(sku, month)] = level if runs and first <= i < first + length else "none"


def placement(ad_level: str) -> float:
    """L6: how much more often the ranker shows an advertised product."""
    return AD_PLACEMENT[ad_level] if ON["L6"] else 1.0


def click_odds(image_count: str, ad_level: str) -> float:
    odds = 1.0
    if ON["L4"]:
        odds *= IMAGE_CLICK_ODDS[image_count]
    if ON["L6"]:
        odds *= AD_CLICK_ODDS[ad_level]
    return odds


def purchase_given_click_odds(image_count: str, description_quality: str) -> float:
    odds = 1.0
    if ON["L4"]:
        odds *= IMAGE_PURCHASE_ODDS[image_count]
    if ON["L5"]:
        odds *= DESCRIPTION_PURCHASE_ODDS[description_quality]
    return odds
