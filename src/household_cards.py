"""Overview's household cards: each group's share of customers and its
average basket, households grouped by the pets they declared (ADR 0033).

Two Aito shapes, both server-side, no per-row fan-out:

  1. **Customer counts** for every group in one `_batch` (five
     `_search limit=0` counts, one round-trip).
  2. **Average basket** per group from one `_aggregate` on `customers`,
     which carries `pets` natively (no link traversal) plus each
     customer's `total_spent_eur` and `total_orders`.
     `mean(total_spent_eur) / mean(total_orders)` is exactly the
     order-weighted mean basket (`Σ spend / Σ orders`), at ~20 ms against
     ~2.9 s for the same aggregate filtered through a link on `orders`
     (ADR 0024).
"""

from __future__ import annotations

from dataclasses import dataclass

from src.aito_client import AitoClient, AitoError


# Keyed by the declared `customers.pets` value. `pets` is a Text column,
# and a bare value compares the whole value: "dog" is dog-only.
HOUSEHOLDS: dict[str, tuple[str, str]] = {
    "dog":          ("🐕", "Dog households"),
    "cat":          ("🐈", "Cat households"),
    "dog cat":      ("🐾", "Dog & cat households"),
    "small_animal": ("🐹", "Small-animal households"),
    "aquarium":     ("🐟", "Aquarium households"),
}


@dataclass(frozen=True)
class HouseholdCard:
    id: str
    emoji: str
    label: str
    customers: int
    share_pct: float
    avg_basket_eur: float
    # Set only on the card that ranks first or last on a number the card
    # shows (see `rank_pill`); every other card has no pill.
    pill_text: str | None
    pill_tone: str | None


def rank_pill(card_id: str, shares: dict[str, float], baskets: dict[str, float]) -> tuple[str, str] | None:
    """The pill a household card earns from the two numbers it shows.

    Pills are derived, never hand-written, so a label can't contradict
    the share or basket printed next to it. A card that ranks on more
    than one number keeps the first pill in this order.
    """
    if card_id == max(baskets, key=baskets.__getitem__):
        return "Highest basket", "orange"
    if card_id == max(shares, key=shares.__getitem__):
        return "Largest group", "blue"
    if card_id == min(baskets, key=baskets.__getitem__):
        return "Lowest basket", "grey"
    return None


def household_cards(client: AitoClient, *, total_customers: int) -> list[HouseholdCard]:
    ids = list(HOUSEHOLDS)
    counts = client.batch([{"from": "customers", "where": {"pets": i}, "limit": 0} for i in ids])

    customers: dict[str, int] = {}
    baskets: dict[str, float] = {}
    for household, count in zip(ids, counts):
        if count["total"] == 0:
            raise AitoError(f"no customer declared pets {household!r}; the household cards expect every group")
        agg = client.aggregate(table="customers", where={"pets": household},
                               aggregate_fields=["total_spent_eur.$mean", "total_orders.$mean"])
        customers[household] = count["total"]
        baskets[household] = round(agg["total_spent_eur.$mean"] / agg["total_orders.$mean"], 2)

    shares = {h: round(n / total_customers * 100, 1) for h, n in customers.items()}
    cards = []
    for household in ids:
        emoji, label = HOUSEHOLDS[household]
        pill = rank_pill(household, shares, baskets)
        cards.append(HouseholdCard(
            id=household, emoji=emoji, label=label, customers=customers[household],
            share_pct=shares[household], avg_basket_eur=baskets[household],
            pill_text=pill[0] if pill else None, pill_tone=pill[1] if pill else None,
        ))
    return cards
