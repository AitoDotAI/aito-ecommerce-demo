"""Product › History: one product's funnel, surfaces, reviews and months.

What the data holds for one product (ADR 0028, ADR 0041), as one `_batch`:

  1. Funnel   — impressions → clicked → added to cart → purchased (counts)
  2. Surfaces — impressions and purchases per surface (counts)
  3. Reviews  — the product's reviews: rating, sentiment and month
  4. Months   — its `product_states` (price, offer, stars, a rival's
                launch, a price rise) and its `monthly_sales` units

Twelve `_search limit: 0` counts and three `_search`es with rows go in
one `_batch`: one round-trip instead of fifteen. Who buys it is
`src/product_buyers.py`.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass

from src.aito_client import AitoClient, AitoError

FUNNEL_STEPS: list[tuple[str, dict]] = [
    ("impressions",   {}),
    ("clicked",       {"clicked": True}),
    ("added_to_cart", {"added_to_cart": True}),
    ("purchased",     {"purchased": True}),
]
SURFACES = ["search", "for_you", "category", "bought_together"]
RATINGS = ["1", "2", "3", "4", "5"]
SENTIMENTS = ["positive", "neutral", "negative"]

# More than any product's reviews or months; `_rows` raises if a table
# has more rows than came back.
ROWS_LIMIT = 500


@dataclass(frozen=True)
class FunnelStep:
    step: str
    count: int


@dataclass(frozen=True)
class SurfaceRow:
    surface: str
    impressions: int
    purchased: int


@dataclass(frozen=True)
class MonthRow:
    """One month the product was on sale: what it sold, and its state."""
    month: str
    units_sold: int
    price_eur: float
    list_price_eur: float
    discount_band: str        # "none" | "10-15" | "15-20" | "20+"
    rating_band: str          # its stars as shown that month: "unrated", "1-2", "3", "4", "5"
    age: str                  # "new" | "established"
    rival_launched: bool      # a rival product launched recently
    price_change: str         # "none" | "rise"
    reviews: int              # reviews written that month


@dataclass
class ProductHistory:
    funnel: list[FunnelStep]
    surfaces: list[SurfaceRow]
    months: list[MonthRow]
    ratings: dict[str, int]          # "1".."5" → reviews
    sentiments: dict[str, int]       # "positive" … → reviews

    def to_dict(self) -> dict:
        return asdict(self)

    def month(self, month: str) -> MonthRow | None:
        return next((m for m in self.months if m.month == month), None)


def history_queries(sku: str) -> list[dict]:
    def count(where: dict) -> dict:
        return {"from": "impressions", "where": {"product_sku": sku, **where}, "limit": 0}

    def rows(table: str, select: list[str] | None = None) -> dict:
        body = {"from": table, "where": {"product_sku": sku}, "limit": ROWS_LIMIT}
        return {**body, "select": select} if select else body

    return (
        [count(w) for _, w in FUNNEL_STEPS]
        + [count({"context.surface": s}) for s in SURFACES]
        + [count({"context.surface": s, "purchased": True}) for s in SURFACES]
        + [rows("reviews", ["created_at", "rating", "sentiment"]),
           rows("product_states"),
           rows("monthly_sales", ["month", "units_sold"])]
    )


def get_product_history(client: AitoClient, sku: str) -> ProductHistory:
    answers = iter(client.batch(history_queries(sku)))
    funnel = [FunnelStep(step, next(answers)["total"]) for step, _ in FUNNEL_STEPS]
    shown = [next(answers)["total"] for _ in SURFACES]
    bought = [next(answers)["total"] for _ in SURFACES]
    reviews, states, sales = [_rows(sku, table, next(answers))
                              for table in ("reviews", "product_states", "monthly_sales")]

    # Every impression has exactly one surface. A mismatch means a surface
    # this view doesn't know.
    if sum(shown) != funnel[0].count:
        raise AitoError(f"{sku}: surfaces {SURFACES} cover {sum(shown)} of {funnel[0].count} impressions")

    return ProductHistory(
        funnel=funnel,
        surfaces=[SurfaceRow(s, i, p) for s, i, p in zip(SURFACES, shown, bought)],
        months=_months(sku, states, sales, reviews),
        ratings=_count_by(sku, reviews, "rating", RATINGS),
        sentiments=_count_by(sku, reviews, "sentiment", SENTIMENTS),
    )


def _rows(sku: str, table: str, answer: dict) -> list[dict]:
    hits = answer["hits"]
    if len(hits) != answer["total"]:
        raise AitoError(f"{sku}: {table} has {answer['total']} rows, but only {len(hits)} came back")
    return hits


def _count_by(sku: str, reviews: list[dict], field: str, values: list[str]) -> dict[str, int]:
    counts = Counter(str(r[field]) for r in reviews)
    unknown = set(counts) - set(values)
    if unknown:
        raise AitoError(f"{sku}: reviews with a {field} this view doesn't know: {sorted(unknown)}")
    return {v: counts[v] for v in values}


def _months(sku: str, states: list[dict], sales: list[dict], reviews: list[dict]) -> list[MonthRow]:
    """One row per month the product was on sale (it has a state then).

    `monthly_sales` may leave out a month with no sales, so a month on
    sale without a sales row sold 0 units. A sale in a month with no
    state would be a sale while not on sale: that raises."""
    units = {row["month"]: int(row["units_sold"]) for row in sales}
    on_sale = {row["month"] for row in states}
    if set(units) - on_sale:
        raise AitoError(f"{sku}: sales in {sorted(set(units) - on_sale)}, with no product_states row")
    reviews_by_month = Counter(r["created_at"] for r in reviews)
    return [
        MonthRow(
            month=s["month"],
            units_sold=units.get(s["month"], 0),
            price_eur=float(s["price_eur"]),
            list_price_eur=float(s["list_price_eur"]),
            discount_band=s["discount_band"],
            rating_band=s["rating_band"],
            age=s["age"],
            rival_launched=bool(s["rival_launched"]),
            price_change=s["price_change"],
            reviews=reviews_by_month[s["month"]],
        )
        for s in sorted(states, key=lambda s: s["month"])
    ]
