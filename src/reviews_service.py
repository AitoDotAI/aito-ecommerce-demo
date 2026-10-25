"""What a product's stars and a customer's reviews go with, shop-wide (ADR 0039).

Four sections, each a `_relate` with an interval (the machinery of Shop analytics,
`src/shop_analytics_service.py`), and one comparison of churn after a reply:

- **clicks / purchases**: `_relate clicked|purchased` on `impressions`, by the
  stars the product had when it was shown (`product_state.rating_band`);
- **NPS**: `_relate nps_group = detractor` on `nps_responses`, by the stars of the
  surveyed order's first product and by whether the respondent wrote a 1-2 star review;
- **churn**: `_relate churned_in_3_months` on `customer_months`, by whether the
  customer wrote a negative review and whether the shop replied.

What this view does not do is read demand off the stars. Shop-wide, 5-star
products sell fewer units than 4-star ones (4.8 against 6.3 a product-month) because
the stars are set by how much a product has sold. The comparison that isolates the
stars is within one product over its own months: Product › History.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from src.aito_client import AitoClient, AitoError
from src.design_effect import DesignEffect
from src.shop_analytics_service import LiftSection, lift_section

FUNNEL_FIELDS = ["product_state.rating_band", "product_state.review_count_band"]
NPS_FIELDS = ["product_state.rating_band", "wrote_negative_review"]
CHURN_FIELDS = ["had_negative_review", "review_replied", "nps_latest_group"]
SECTIONS = ("clicked", "purchased", "nps", "churn")
Z95 = 1.959964


@dataclass(frozen=True)
class ReplyEffect:
    """Churn within 3 months of customers who wrote a negative review, replied ÷ not replied."""
    replied_months: int
    replied_churned: int
    unreplied_months: int
    unreplied_churned: int
    risk_ratio: float
    interval_low: float
    interval_high: float
    verdict: str            # "fewer leave" | "more leave" | "a tie"

    def to_dict(self) -> dict:
        return asdict(self)


def get_reviews_section(client: AitoClient, section: str) -> LiftSection:
    if section not in SECTIONS:
        raise ValueError(f"Unknown reviews section {section!r}; expected one of {SECTIONS}")
    if section in ("clicked", "purchased"):
        return lift_section(client, table="impressions", customer_field="context.customer",
                            month_field="context.month", condition={section: True},
                            fields=FUNNEL_FIELDS, selected=section, options=[])
    if section == "nps":
        return lift_section(client, table="nps_responses", customer_field="customer", month_field="month",
                            condition={"nps_group": "detractor"}, fields=NPS_FIELDS, selected=section, options=[])
    return lift_section(client, table="customer_months", customer_field="customer_id", month_field="month",
                        condition={"churned_in_3_months": True}, fields=CHURN_FIELDS, selected=section, options=[])


def get_reply_effect(client: AitoClient, clustering: DesignEffect) -> ReplyEffect:
    """Among customer-months with a negative review: churn when the shop replied ÷ when it did not.

    The interval treats customer-months as independent and is widened by the churn
    section's design effect, since one customer contributes several months."""
    def count(where: dict) -> int:
        return client.search("customer_months", where=where, limit=0)["total"]

    negative = {"had_negative_review": True}
    replied = {**negative, "review_replied": True}
    unreplied = {**negative, "review_replied": False}
    r_n, r_c = count(replied), count({**replied, "churned_in_3_months": True})
    u_n, u_c = count(unreplied), count({**unreplied, "churned_in_3_months": True})
    if min(r_c, u_c) == 0:
        raise AitoError(f"reply effect: {r_c} churned of {r_n} replied, {u_c} of {u_n} unreplied; too few to compare")
    ratio = (r_c / r_n) / (u_c / u_n)
    se = math.sqrt((1 / r_c - 1 / r_n + 1 / u_c - 1 / u_n) * clustering.design_effect)
    low, high = math.exp(math.log(ratio) - Z95 * se), math.exp(math.log(ratio) + Z95 * se)
    verdict = "fewer leave" if high < 1 else "more leave" if low > 1 else "a tie"
    return ReplyEffect(r_n, r_c, u_n, u_c, ratio, low, high, verdict)
