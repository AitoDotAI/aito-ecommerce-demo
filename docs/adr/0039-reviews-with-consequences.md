# ADR 0039: Reviews with consequences — clicks, purchases, NPS, churn, demand and price

**Status:** Proposed
**Date:** 2026-10-24
**Deciders:** Antti

## Context

Reviews are the clearest case of one fact touching every part of a shop: a
product's experience shows up in its stars, the stars move clicks and
sales, and the experience itself moves whether the buyer recommends the
shop and comes back. The demo should show that chain end to end, each
link measurable in analytics.

Today the generator runs it backwards and only partly:

- **Churn writes the reviews.** A customer who is going to churn is more
  likely to write a 1-star review, and the review's `churn_within_90d`
  label is copied from that customer's churn. A churn view that reads
  "1-star reviews predict churn" is true of the data for the wrong reason.
- **Stars move only clicks and conversion** (ADR 0032's P4).
- **A product's quality is a hidden yes/no** ("poorly made", from a hash),
  and it lowers conversion only.
- **There's no NPS.**

## Decision

### The chain, causal and in one direction

```
quality (hidden, per product)
   └─► experience of each purchase (good / ok / bad; plus a delivery incident)
          ├─► a review, sometimes (rating, text, category)
          │      └─► stars and review count (product_states, ADR 0032/0038)
          │             ├─► clicks and purchases (R1, R2)
          │             ├─► demand, units per month (R5)
          │             └─► price sensitivity (R6)
          ├─► NPS, when surveyed (R3)
          └─► churn (R4)
```

- **Quality** replaces "poorly made" with four levels: `poor` 8 %, `ok`
  42 %, `good` 40 %, `excellent` 10 %, fixed per product from a hash, as
  now.
- **Experience** of each order line is drawn from its product's quality;
  a delivery incident (late, damaged) is drawn per order at 6 %.
- **Reviews** are written after a share of orders: 25 % after a bad
  experience, 8 % after an ok one, 15 % after a good one. The rating comes
  from the experience. The shop's reply is new (`replied`, within the
  month, 40 % of negative reviews, chosen at random).

### Planted effects

| # | Effect | Planted as |
|---|---|---|
| R1 | Stars move clicks | ADR 0038's P7, by stars sensitivity |
| R2 | Stars move purchases | P7 on purchase; plus quality itself: a `poor` product's impression converts at ×0.6 whatever its stars (the reason stars matter) |
| R3 | Experience moves NPS | a new `nps_responses` table: a survey after 30 % of orders, score 0–10. Base 8.0 (σ 1.5); a bad experience −3.5, a delivery incident −2.0, an excellent one +0.7. **For the reviewer and every other buyer alike:** the review is the shop's sight of a bad experience, not its cause. A reply to a negative review recovers +2.0 for its writer |
| R4 | Experience moves churn | each bad experience raises the shopper's monthly churn hazard ×1.8 for 3 months; a reply to their negative review halves that rise. Churn is drawn after experiences, replacing the reversed copy |
| R5 | Stars move demand | a product's order-pick weight follows its rating band: 5 stars ×1.3, 1–2 stars ×0.6, so `monthly_sales` units carry it |
| R6 | Stars move price sensitivity | the price elasticity ε of a 5-star product is −1.0, of a 1–2 star one −2.4 (between: as now). A well-rated product holds its units through a price rise |

Each effect is judged against its null generation, on every seed. The
thresholds are pre-registered in `docs/verification/actionable-states-prereg.md`
(shared with ADR 0038), e.g.:
- NPS of buyers after a bad experience ≤ base − 2.5;
- churn after a bad experience ≥ 1.4× the null;
- a replied review's writer churns ≤ 0.75× an unreplied one's;
- the 5-star / 1–2-star demand ratio ≥ 1.8.

### New and changed tables

| Table | Change |
|---|---|
| `reviews` | gains `replied` (Boolean), `order_line` (link). `churn_within_90d` is computed from the churn that actually followed, not copied |
| `nps_responses` | new: `customer` (link), `month`, `score`, `nps_group` (`promoter` 9–10, `passive` 7–8, `detractor` 0–6), `order` (link, the order surveyed) |
| `order_lines` | gains `incident` (Boolean, delivery). The experience stays hidden, as a shop only sees it through reviews, NPS and returns |
| `customer_months` | gains `nps_latest_group`, `had_negative_review`, `review_replied` |

### Analytics: a Reviews view

One page, one product or the whole shop, each row an Aito query with an
interval:

| Effect | Query |
|---|---|
| on CTR | `_relate clicked` on `impressions`, by `product_state.rating_band` |
| on purchases | the same for `purchased` |
| on NPS | `_relate nps_group = detractor` on `nps_responses`, by `order`'s product's rating band, and by the respondent having written a negative review |
| on churn | `_relate churned_in_3_months` on `customer_months`, by `had_negative_review` and `review_replied` |
| on demand | `_estimate units` on `monthly_sales`, with `$why`'s rating-band factor (ADR 0032's Q4 form) |
| on pricing | the price what-if (ADR 0029) for the same product at its real stars and at one band lower |

**The headline action:** "Replying to a negative review halves its writer's
added churn." It's actionable, and it's planted at random, so it's
identifiable.

The Churn and Win-back views' copy about reviews is reviewed: "1-star
reviews predict churn" becomes "bad experiences raise churn; a negative
review is how the shop sees one".

## Aito usage, and what to probe first

| # | Shape | Question |
|---|---|---|
| Q10 | `_relate` on `nps_responses` → `order.order_lines.product_state.rating_band` | Does relate go through a link to a one-to-many child? If not, NPS rows gain the product's band at the time (derived, as ADR 0033 allows) |
| Q11 | `_relate churned_in_3_months` → `review_replied` on `customer_months` | Boolean relate, the known form |
| Q12 | `_estimate units` with `product_state.rating_band` in `where`, `$why` | Does the band enter as a factor? |

## Acceptance criteria

- [ ] R1–R6 pass their pre-registered checks against null generations, on
      every seed.
- [ ] No data path makes churn cause a review. A test runs the generator
      with reviews disabled and checks the churn rate doesn't change.
- [ ] A user can open the Reviews view and see each of the six effects with
      an interval, for the whole shop and for one product.
- [ ] A user can see that replied negative reviews are followed by less
      churn than unreplied ones, with the interval.
- [ ] The Churn and Win-back copy no longer says reviews predict churn.

## Demo impact

A new owner beat: "One badly made product: its 1-star reviews cut its
clicks, its sales and its demand forecast, and its buyers' NPS fell,
including those who never wrote a review. Where the shop replied, fewer
of them left."

## Out of scope

- Generating review text that reflects quality beyond today's templates.
- Returns and refunds as a separate signal.
- Sentiment analysis of review text (the text stays templated).

## Consequences

**Good:**
- One hidden cause, visible in six measured effects: the most direct "360°"
  story the data can tell.
- The reversed review→churn copy goes away.

**Bad:**
- Churn's drivers change, so the Churn and Win-back views' planted
  effects are re-checked.
- Two more tables, in the same release as ADR 0038.
