"""The showing funnel of a segment: impressions, clicks, carts, purchases (ADR 0053).

Counted over the ranked showings the shop holds (`impressions`, the table the Shop analytics view reads), those in a session that
belongs to a profiled customer. A session carries a customer once the visitor is identified; on the release that is all but six of
43,390 showings (a tripwire in aito-check), so the funnel describes identified shoppers, and says so.
"""

from __future__ import annotations

from collections import defaultdict

STAGES = ("impressions", "clicks", "carts", "purchases")


def funnel_by_segment(impressions: list[dict], customer_of_context: dict[str, str | None],
                      segments_of_customer: dict[str, list[str]]) -> dict[str, dict]:
    """For each segment key, the counts at each stage, over the showings of the customers in it."""
    out: dict[str, dict[str, int]] = defaultdict(lambda: dict.fromkeys(STAGES, 0))
    for showing in impressions:
        customer = customer_of_context.get(showing["context"])
        for key in segments_of_customer.get(customer, ()):
            counts = out[key]
            counts["impressions"] += 1
            counts["clicks"] += bool(showing["clicked"])
            counts["carts"] += bool(showing["added_to_cart"])
            counts["purchases"] += bool(showing["purchased"])
    return dict(out)
