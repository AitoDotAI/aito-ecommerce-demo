"""The Product view (ADR 0041): one product, one month, its levers.

"What will this product do, why, and what if I change its price or
discount? For whom?" — the product manager's question, answered from
what today's data holds (ADR 0038 describes the fuller version):

- **The decision:** which discount band earns the most per showing
  (`src/product_decision.py`, from the discount what-if), and next
  month's units and profit at today's price and at that band's price
  (the price what-if).
- **What if:** the discount bands (`src/discount_what_if.py`); the
  price curve and its what-if are their own endpoints, as the user
  moves the price (`src/price_curve.py`, `src/price_what_if.py`).
- **History:** funnel, surfaces, reviews and the months with their
  states (`src/product_history.py`).
- **For whom:** who buys it (`src/product_buyers.py`).

The what-ifs forecast the month after the data ends (FORECAST_MONTH);
the month asked about sets which state is "now": its price and band.
Cached 30 min per product and month.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

from src import cache
from src.aito_client import AitoClient, AitoError
from src.category_anchors import humanise
from src.demand_forecast import FORECAST_MONTH, LATEST_MONTH
from src.discount_what_if import DiscountWhatIf, get_discount_what_if, predict_body
from src.lookup_errors import ProductNotOnSaleError, UnknownProductError
from src.price_what_if import PriceWhatIf, get_price_what_if
from src.product_buyers import BuyerRow, ShopperLink, get_buyers, shopper_for
from src.product_decision import OfferDecision, decide_offer
from src.product_history import MonthRow, ProductHistory, get_product_history

CATALOG_FILE = Path(__file__).resolve().parent.parent / "data" / "products.json"

# The product the view opens on. Picked from the data for its story: of
# the products that had an offer, a price rise and a rival's launch in
# their 24 months, and are at list price in the latest month, it is among
# the three that sold the most units (data release 3a moved the order of two close ones). PetNord Grain Free Daily Dental Treats 80g (data release 2): a
# price rise in May 2025, a rival in June 2025, 20 %+ off in September 2025
# and March 2026, and dental treats are what dog dry-food buyers add
# (Patterns › Baskets). `tests/test_product_service.py` checks that story
# against the data.
DEFAULT_SKU = "SKU-PT-0194"


@dataclass
class ProductView:
    product: dict                     # sku, name, brand, pet_type, category, price_eur, unit_cost_eur
    month: str                        # the month asked about: its state is "now"
    forecast_month: str               # the month the what-ifs estimate
    state: MonthRow                   # the product in `month`
    decision: OfferDecision
    discount: DiscountWhatIf
    price_now: PriceWhatIf            # next month at the price in `month`
    price_best: PriceWhatIf | None    # next month at the advised band's price; None when it is "keep"
    history: ProductHistory
    buyers: list[BuyerRow]
    shopper: ShopperLink | None       # the Shop shopper to see it as
    basket_category: dict             # {"token": "dog_dentaltreats", "label": "Dog dental-treats"}
    candidates: list[dict]            # the picker: sku, name, brand, category, pet_type
    last_query: dict

    def to_dict(self) -> dict:
        return asdict(self)


def load_catalog() -> dict[str, dict]:
    rows = json.loads(CATALOG_FILE.read_text())
    return {p["sku"]: p for p in rows}


def product_view_payload(client: AitoClient, sku: str | None, month: str = LATEST_MONTH) -> dict:
    """The view as the API returns it, cached per product and month."""
    sku = sku or DEFAULT_SKU
    key = f"product-view:{sku}:{month}"
    cached = cache.get(key)
    if cached:
        return cached
    payload = get_product_view(client, sku, month).to_dict()
    cache.set(key, payload, ttl=1800)
    return payload


def get_product_view(client: AitoClient, sku: str, month: str = LATEST_MONTH) -> ProductView:
    catalog = load_catalog()
    if sku not in catalog:
        raise UnknownProductError(f"No product {sku} in the catalogue")

    with ThreadPoolExecutor(max_workers=4) as pool:
        history_job = pool.submit(get_product_history, client, sku)
        buyers_job = pool.submit(get_buyers, client, sku)
        discount_job = pool.submit(get_discount_what_if, client, sku, month)
        cost_job = pool.submit(_unit_cost, client, sku)
        history = history_job.result()
        state = history.month(month)
        if state is None:
            on_sale = [m.month for m in history.months]
            raise ProductNotOnSaleError(
                f"{sku} was not on sale in {month}; it was from {on_sale[0]} to {on_sale[-1]}"
                if on_sale else f"{sku} was never on sale")
        discount, cost, buyers = discount_job.result(), cost_job.result(), buyers_job.result()

    decision = decide_offer(discount.bands, state.list_price_eur, cost)
    with ThreadPoolExecutor(max_workers=2) as pool:
        now_job = pool.submit(get_price_what_if, client, sku, state.price_eur)
        best_job = (pool.submit(get_price_what_if, client, sku, decision.best.price_eur)
                    if decision.action != "keep" else None)
        price_now, price_best = now_job.result(), best_job.result() if best_job else None

    product = catalog[sku]
    return ProductView(
        product={**{k: product[k] for k in ("sku", "name", "brand", "pet_type", "category", "price_eur")},
                 "unit_cost_eur": cost},
        month=month,
        forecast_month=FORECAST_MONTH,
        state=state,
        decision=decision,
        discount=discount,
        price_now=price_now,
        price_best=price_best,
        history=history,
        buyers=buyers,
        shopper=shopper_for(buyers),
        basket_category={"token": f"{product['pet_type']}_{product['category'].replace('-', '')}",
                         "label": humanise(product["pet_type"], product["category"])},
        candidates=[
            {k: p[k] for k in ("sku", "name", "brand", "category", "pet_type")}
            for p in sorted(catalog.values(), key=lambda p: (p["pet_type"], p["category"], p["name"]))
        ],
        last_query={"endpoint": "_predict", "body": predict_body(sku, decision.best_band)},
    )


def _unit_cost(client: AitoClient, sku: str) -> float:
    hits = client.search("inventory", where={"sku": sku}, limit=1)["hits"]
    if not hits:
        raise AitoError(f"{sku} has no inventory row, so it has no unit cost")
    return float(hits[0]["unit_cost_eur"])
