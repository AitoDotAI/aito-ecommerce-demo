"""The owner's levers, in the sandbox only (ADR 0043): an offer, a review.

Both write the product's **next month**, 2026-05 (the data ends in
2026-04). A past month is never rewritten: that would relabel history's
impressions and change what Aito learned from them.

- **Offer** {sku, band}: the product's 2026-05 `product_states` row, its
  price and discount from April's list price at the band's typical
  discount (`product_decision.BAND_DISCOUNT_PCT`).
- **Review** {sku, stars, text}: a `reviews` row dated 2026-05, then the
  2026-05 state again, its `rating_band` recomputed.

`rating_band` follows the generator's rule (`data/shoppers.py:
rating_band`) over all the product's reviews so far, the new one
included: the owner is shown what one more review does to the stars.

Every write is one v2 `POST /data/_modify` (Aito's schema-migration docs,
`api-docs/content/schema-migration-v2.md`): `{"into": t, "insert": row}`
for May's first state and each review, `{"update": t, "set": …, "where":
{key}}` when a lever already wrote May (Aito core measured 8 ms for the
insert, 33–86 ms for the update, on 2.11.8). The row is then read back from
the sandbox, and only what was read is returned: the reaction is shown from
the database, not from what the app meant to write.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass

from src.aito_client import AitoClient, AitoError
from src.demand_forecast import LATEST_MONTH
from src.discount_what_if import BANDS
from src.lookup_errors import UnknownProductError
from src.product_decision import BAND_DISCOUNT_PCT
from src.shop_history import NEXT_MONTH


MAX_REVIEWS = 500
# Who writes the owner's review: Päivi, the Shop's guinea-pig shopper
# (`src/shop_personas.py`). A review must link to a customer.
REVIEWER = "CUST-01177"
# The labels a triage would give a review (`reviews` holds them for the
# Feedback view): its sentiment by stars, and the team that takes it.
SENTIMENT = {1: "negative", 2: "negative", 3: "neutral", 4: "positive", 5: "positive"}
CATEGORY = {1: "quality", 2: "quality", 3: "quality", 4: "praise", 5: "praise"}
ASSIGNED_TO = {"quality": "Petri", "praise": "Joonas"}


class LeverInputError(ValueError):
    """A lever asked for something the data can't hold (a band, a star count)."""


@dataclass(frozen=True)
class LeverResult:
    sku: str
    lever: str                      # "offer" | "review"
    state: dict                     # the 2026-05 product_states row, as read back
    rating_band_before: str         # the 2026-05 stars before this lever
    rating_band_changed: bool
    reviews: int                    # the product's reviews, the new one included
    avg_rating: float | None
    review: dict | None             # the review row, as read back

    def to_dict(self) -> dict:
        return asdict(self)


def set_offer(client: AitoClient, sku: str, band: str) -> LeverResult:
    if band not in BANDS:
        raise LeverInputError(f"Unknown discount band {band!r}; one of {', '.join(BANDS)}")
    april = _state(client, sku, LATEST_MONTH)
    if april is None:
        raise UnknownProductError(f"{sku} has no {LATEST_MONTH} state: it isn't on sale")
    before = _state(client, sku, NEXT_MONTH)
    ratings = _ratings(client, sku)
    state = _write_state(client, next_month_state(april, band, rating_band_of(ratings)), exists=before is not None)
    previous = before["rating_band"] if before else april["rating_band"]
    return LeverResult(sku, "offer", state, previous, state["rating_band"] != previous,
                       len(ratings), _mean(ratings), None)


def add_review(client: AitoClient, sku: str, stars: int, text: str) -> LeverResult:
    if stars not in SENTIMENT:
        raise LeverInputError(f"A review has 1 to 5 stars, not {stars}")
    if not text.strip():
        raise LeverInputError("A review needs some text")
    april = _state(client, sku, LATEST_MONTH)
    if april is None:
        raise UnknownProductError(f"{sku} has no {LATEST_MONTH} state: it isn't on sale")
    before = _state(client, sku, NEXT_MONTH)
    previous = before["rating_band"] if before else april["rating_band"]

    review = _write_review(client, review_row(sku, stars, text))
    ratings = _ratings(client, sku)
    if review["review_id"] not in {r["review_id"] for r in ratings}:
        raise AitoError(f"The review {review['review_id']} was written but {sku}'s reviews don't hold it")
    # Keep the owner's offer if one was set; a fresh 2026-05 state starts at list price.
    band = before["discount_band"] if before else "none"
    state = _write_state(client, next_month_state(april, band, rating_band_of(ratings)), exists=before is not None)
    return LeverResult(sku, "review", state, previous, state["rating_band"] != previous,
                       len(ratings), _mean(ratings), review)


def read_states(client: AitoClient, sku: str) -> dict:
    """{"april": row, "next": row or None}: what the lever panel starts from."""
    april = _state(client, sku, LATEST_MONTH)
    if april is None:
        raise UnknownProductError(f"{sku} has no {LATEST_MONTH} state: it isn't on sale")
    return {"april": april, "next": _state(client, sku, NEXT_MONTH), "next_month": NEXT_MONTH}


def next_month_state(april: dict, band: str, rating_band: str) -> dict:
    """The 2026-05 row: April's list price at `band`'s typical discount, and
    April's age, rival and price-change facts carried forward."""
    list_price = float(april["list_price_eur"])
    discount_pct = BAND_DISCOUNT_PCT[band]
    return {
        "product_state_id": f"{april['product_sku']}-{NEXT_MONTH}",
        "product_sku": april["product_sku"],
        "month": NEXT_MONTH,
        "price_eur": round(list_price * (1 - discount_pct / 100), 2),
        "list_price_eur": list_price,
        "discount_pct": discount_pct,
        "on_offer": band != "none",
        "discount_band": band,
        "rating_band": rating_band,
        "age": april["age"],
        "rival_launched": april["rival_launched"],
        "price_change": april["price_change"],
    }


def review_row(sku: str, stars: int, text: str) -> dict:
    category = CATEGORY[stars]
    return {
        "review_id": f"REV-SANDBOX-{uuid.uuid4().hex[:10]}",
        "customer_id": REVIEWER,
        "product_sku": sku,
        "rating": stars,
        "text": text.strip(),
        "category": category,
        "sentiment": SENTIMENT[stars],
        "assigned_to": ASSIGNED_TO[category],
        "created_at": NEXT_MONTH,
        "churn_within_90d": False,
    }


def rating_band_of(ratings: list[dict]) -> str:
    # Imported here, not at the top: the generator's package is a build-time
    # tool, and only the sandbox's levers need its rule at run time.
    from data.shoppers import rating_band
    return rating_band(_mean(ratings))


def _mean(ratings: list[dict]) -> float | None:
    return sum(int(r["rating"]) for r in ratings) / len(ratings) if ratings else None


def _state(client: AitoClient, sku: str, month: str) -> dict | None:
    res = client.search("product_states", where={"product_sku": sku, "month": month}, limit=2)
    if res["total"] > 1:
        raise AitoError(f"{sku} has {res['total']} product_states rows for {month}, expected at most one")
    return res["hits"][0] if res["hits"] else None


def _ratings(client: AitoClient, sku: str) -> list[dict]:
    res = client.search("reviews", where={"product_sku": sku}, select=["review_id", "rating"], limit=MAX_REVIEWS)
    if res["total"] > len(res["hits"]):
        raise AitoError(f"{sku} has {res['total']} reviews, more than the {MAX_REVIEWS} read")
    return res["hits"]


def _write_state(client: AitoClient, row: dict, *, exists: bool) -> dict:
    """Insert May's row, or update it in place when a lever already wrote it."""
    key = {"product_state_id": row["product_state_id"]}
    if exists:
        changes = {k: v for k, v in row.items() if k not in key}
        client._request("POST", "/data/_modify", json={"update": "product_states", "set": changes, "where": key})
    else:
        client._request("POST", "/data/_modify", json={"into": "product_states", "insert": row})
    return _read_back(client, "product_states", key, row)


def _write_review(client: AitoClient, row: dict) -> dict:
    client._request("POST", "/data/_modify", json={"into": "reviews", "insert": row})
    return _read_back(client, "reviews", {"review_id": row["review_id"]}, row)


def _read_back(client: AitoClient, table: str, where: dict, written: dict) -> dict:
    """The row as the database now holds it; raises unless it is exactly the one written."""
    res = client.search(table, where=where, limit=2)
    if res["total"] != 1:
        raise AitoError(f"Read back {res['total']} {table} rows for {where} after writing one")
    row = res["hits"][0]
    differs = {k: (v, row.get(k)) for k, v in written.items() if row.get(k) != v}
    if differs:
        raise AitoError(f"{table} row {where} read back differently from what was written: {differs}")
    return {k: row[k] for k in written}
