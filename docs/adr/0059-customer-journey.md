# ADR 0059: The journey of a segment: the months around the last order, those who left against those who stayed

**Status:** Accepted (2026-11-01, Antti: "lets do the recommendation"). Slice 1 built: the segment's journey. Not built: the path of a single customer (see Out of scope).
**Date:** 2026-11-01
**Deciders:** Antti

## Context

Antti asked for a customer journey that marks visits, purchases, reviews, feedback, returns, actions and churn, to explain feedback and churn. Each of those
events is in a table with a month on it (`contexts` / `customer_months`, `orders`, `order_lines`, `reviews`, `nps_responses`, `customer_actions`), and
none is finer than a month. So the data says which months an event fell in, not the order of events within a month. The Customers view
also promises that no row says who it is about (ADR 0055); a timeline of one named customer would break that promise, so the first slice is an aggregate.

## Decision

A **Journey** tab on the Customers view, for the selected segment. Each customer is lined up on their own **last order** (month 0), from five months before it to
two after. For each kind of event and each month, the grid shows the share of the customers who left (those the shop counts as churned: no order in the last three
months of the data) and of those who stayed with that event in the month, and whether the difference is beyond chance (99.7 %, the margin used elsewhere
for differences of shares). The events: ordered, visited the shop, returned a line, a late or damaged delivery, a 1–2 star review, a 0–6 answer to the NPS
survey, and an action the shop sent. A group under 30 customers is not compared. A month beyond the data is left out of the cell for the customers whose offset falls there.

The events by customer and month are stored (`data/customer_profiles/journeys.json`, written by `./do customer-profiles`, checked against a rebuild); the route
`/api/customer-profiles/journey?c=…` lines the selection up. No customer id appears in the answer.

## What the data shows (all customers, stored data)

- **They fade out.** Those who left ordered and visited less in every month before their last order, clearly so from five months before for visits and four for orders;
  visits fall earliest. The less engaged are the ones who leave.
- **The shop reacts.** In the last-order month and the two after, those who left were sent clearly more actions (13–15 % a month against 0–5 %): the win-back, working as designed.
- **No spike of complaints before leaving.** Returns, late deliveries, low reviews and detractor answers are a little higher in the last-order month for those who left
  (12 % returned against 9 %, 8 % low reviews against 6 %), and the difference is not beyond chance. The planted chain (a bad experience raises the churn hazard for three
  months, ADR 0039) is real but small next to the fade-out. A journey that claimed "complaints lead to churn" would claim more than this data shows.

## Aito usage

None: counted from the stored events, like the rest of the view.

## Acceptance criteria

- [ ] A user can open a Journey tab for any segment and see, per event and month around the last order, the shares of those who left and those who stayed.
- [ ] A difference beyond chance is shaded; a group under 30 customers is not compared and says so.
- [ ] No customer id or name is in the route's answer, and a selection under 30 customers gets its size and no grid.
- [ ] The stored events are the ones the fixtures build today.

## Demo impact

`docs/demo-script.md`: the Customers section can open Journey and say what it shows (fade-out, the shop's reaction, and that complaints are not the story).

## Out of scope

The path of a single customer (a timeline of one person's events). It shows one person's history, reverses the removal of the customer lookup and needs Antti's decision; if
allowed it would be anonymous ("customer 1,204"), consenting customers only. Days or weeks (the data is monthly). Causes: this shows what came before leaving, not what caused it.

## Idea, not built: the path around an event (Antti, 2026-11-01)

Like the journey of a web visit in an analytics tool: pick an event, and see what came before it and what came after. Antti's sketch, for the event *gave a detractor NPS answer*:

| Previous event | → Detractor feedback → | Next event | Then |
|---|---|---|---|
| 15 % bought a 1-star product | | 25 % did not visit | – |
| 10 % bought a 2-star product | | 20 % an action was sent | 8 % visited |
| 9 % a late delivery | | 15 % visited, no purchase | |

What the data would allow, as far as the stored tables go:
- **Events per customer and month** exist for visits, orders, returns, late or damaged deliveries, reviews (with their stars), NPS answers (with their scores) and the shop's actions. `customer_months` has a row for every month a customer is observed, so "did not visit" (visits = 0) and "visited, did not order" (visits > 0, purchases = 0) are events too.
- **"Previous", "next" and "then" are months**: the month before the event, the month after, and the month after that among those who had a given next event. The order of events *within* a month is not known, so an event in the same month as the anchor cannot be called before or after it.
- **Each row can be set against how the segment usually looks** (the share of all its customer-months with that event) and called a pattern with the same words as elsewhere (Pattern?: Yes, Likely, Possibly, Unlikely).
- "Bought a 1-star product" is not in the stored events: a customer's own review stars are, a product's average rating at the time of purchase would have to be added.
- A path is an aggregate like the rest of the view: no customer is shown, and an event with fewer than 30 occurrences gets its count and no path.

The "months around the last order" grid above is the special case with *the last order* as the anchor. Not scheduled; written down on Antti's word, 2026-11-01.
