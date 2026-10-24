# ADR 0040: Where customers come from — sources, landing pages, first orders and who stays

**Status:** Accepted (2026-10-24, Antti: "review, fix and merge all on green")
**Date:** 2026-10-24
**Deciders:** Antti

## Context

A shop owner's first marketing questions are about sources:
- which channels bring visitors who buy;
- which pages they land on;
- which new customers become regulars.

The data can't answer any of them. Every session belongs to an existing
customer, a session's `surface` is a place in the shop (search, For You,
category), not a traffic source, and nobody visits without buying
eventually.

## Decision

### Visitors and sources

- **Anonymous visitors.** A visitor is identified per device (`visitor`,
  e.g. `VIS-0012345`) before they buy. Sessions of visitors who never buy
  are generated too, so conversion has a denominator. On a first
  purchase the visitor becomes a customer, and `customers.visitor` keeps
  the link.
- **Each context gains:**
  - `source`: `organic_search`, `paid_search`, `social`, `email`,
    `affiliate`, `direct`;
  - `landing`: `product`, `category`, `search`, `home`, `offer`;
  - `landing_category`;
  - `visitor`.
- **Each customer gains:**
  - `first_source`: the source of the session with their first order;
  - `joined_month`, as now.

### Planted effects

| # | Effect | Planted as |
|---|---|---|
| F1 | Sources land differently | organic search lands on product pages of the searched category (70 %); social on toys and treats (55 %); email and affiliate on offers (60 %) |
| F2 | Sources convert differently | a new visitor's session converts at: email 6 %, paid search 4 %, organic search 3 %, direct 5 %, affiliate 3.5 %, social 1.2 % |
| F3 | Sources bring different customers | ADR 0038's sensitivities: an affiliate (coupon site) customer is discount-`high` at 2.5×; a social one newness-`high` at 2× |
| F4 | Sources stay differently | a new customer's chance of 3 or more orders in their first 6 months: organic search ×1.4, email ×1.2, direct ×1.0, paid search ×0.9, social ×0.6, affiliate ×0.5 (the coupon hunter leaves when the offer ends) |
| F5 | The first basket says who stays | a first order that includes a staple (food, litter) doubles the chance of becoming regular, whatever the source |

F3 and F4 together give the demo's sharpest finding: affiliates convert
well, but their customers buy on offer and don't stay. Each effect is
judged against its null generation, with thresholds in the shared
pre-registration (ADRs 0038–0039).

### The owner's view: Acquisition

1. **The funnel by source:** visits → sessions with a cart → first order →
   regular within 6 months. Counts from the data, and the Aito estimate
   for each step with an interval.
2. **Where they land, and what they buy:** `_relate` from a source to its
   landing category and its first-order categories.
3. **Will this cohort stay?** For the newest month's new customers, Aito's
   `_predict` of becoming regular from their first source and their first
   basket, with `$why` ("a staple in the first basket ×2.0", "from an
   affiliate ×0.5").
4. **Value by source:** 6-month spend of new customers by source, so a
   source's conversion and its customers' value sit side by side.

`became_regular` (3+ orders in the first 6 months) is a label computed
from later data, as `churned_in_3_months` is. It exists only for
customers who joined at least 6 months before the data ends; the view says
so for recent cohorts.

## Aito usage, and what to probe first

| # | Shape | Question |
|---|---|---|
| Q13 | `_predict became_regular` on `customers`, `where {first_source, first_basket_categories}` | Is `$p` calibrated on held-out cohorts? Do both lifts appear in `$why`? |
| Q14 | `_relate` on `contexts`, `source` → `landing_category` | The known field relate, on a new field |
| Q15 | `_predict purchased` on `impressions` with `context.source` and `context.visitor` set and no customer | Does a session without a customer link score? (The visitor's first session) |

## Acceptance criteria

- [ ] F1–F5 pass their pre-registered checks against null generations.
- [ ] A user can open Acquisition and see the funnel per source, with
      counts and Aito's estimates.
- [ ] A user can see, for the newest cohort, which new customers Aito
      expects to become regular and why.
- [ ] Affiliate shows a high conversion and a low regular rate, each with
      an interval, side by side.
- [ ] Customer-facing copy never names a person; visitors are ids.

## Demo impact

A new owner beat: "Affiliates bring buyers, but they buy on offer and are
gone in three months. Organic search brings fewer, and they stay. For this
month's new customers, here's who Aito expects to become a regular, and
the first basket is why."

## Out of scope

- Ad spend, CAC and ROI: there's no cost data. A cost per source could be
  configured later, labelled as an assumption.
- Multi-touch attribution. A session has one source, and a customer keeps
  their first.
- Real analytics integrations (GA4 and others).

## Consequences

**Good:**
- The owner's views go from "what sells" to "who arrives, and who stays".
- F3 ties sources to ADR 0038's sensitivities, so the views tell one story
  across ADRs.

**Bad:**
- Anonymous sessions grow the impressions table (an estimated +40 %), and
  with it the load and the Shop queries' cost. Measured on the test env
  before the views.
- `customers` gains a link to visitors that only some rows have; probed
  (Q15).
