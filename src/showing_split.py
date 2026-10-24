"""Which showings the shop's ranker learns from, and which it doesn't (ADR 0045, amendment 3).

The generated log holds every moment a product was put in front of someone.
Three kinds of it are not a ranking decision:

- a visitor's **landing page** (the page picks products; nobody buys from it),
- the household's **buy-again** list (what they came for, bought 80 % of the time),
- the **checkout** add-ons (bought 90 % of the time).

Left in one table, these hide an offer's effect. Offered products sit on
landing pages more and on buy-again lists less than other products, and
Aito's `_predict` multiplies each condition's lift as if the conditions were
independent, so a query cannot condition the confound away: on release 2 the
shop-wide lift of a 20 %+ offer on `purchased` read ×0.90, while in the ranked
list alone a showing with the offer is bought ×2.0–2.2 as often.

So the log is loaded as two tables of the same shape: `impressions`, the
showings the shop ranked, and `unranked_showings`, the rest. A shop trains its
ranker on its own ranking decisions; the other table keeps every sale and every
visit queryable (Acquisition reads the landing pages).
"""

from __future__ import annotations

RANKED_PLACEMENT = "list"
NOT_RANKED_SURFACE = "landing"


def split_showings(showings: list[dict], contexts: list[dict]) -> tuple[list[dict], list[dict]]:
    """(ranked, unranked): ranked is a `list` placement on a surface the shop ranks.

    Raises if a showing's context is unknown, so no row can drop out of both."""
    surface = {c["context_id"]: c["surface"] for c in contexts}
    ranked: list[dict] = []
    unranked: list[dict] = []
    for showing in showings:
        context = showing["context"]
        if context not in surface:
            raise ValueError(f"showing {showing['impression_id']} is in context {context}, which is not in contexts")
        is_ranked = showing["placement"] == RANKED_PLACEMENT and surface[context] != NOT_RANKED_SURFACE
        (ranked if is_ranked else unranked).append(showing)
    assert len(ranked) + len(unranked) == len(showings)
    return ranked, unranked
