# ADR 0053: Customer profiles — how customers shop, and who responds to what

**Status:** Accepted, slice 1 built (2026-10-31, Antti: "add the customer analytics view"). Built: the traits, the segment tables with revenue, the response table, the relations between variables, what each group buys, and a lookup, from stored data (slice 2 added revenue, relations and preferences, same day). Not built: live Aito predictions per segment, loyalty use, a customer-facing "your profile" page, withdrawing consent as an action in the demo.
**Date:** 2026-10-31
**Deciders:** Antti

## Context

A shop can tell a lot about how a customer chooses from what they bought: whether they buy on offer, pick the cheaper
products or the better rated ones, which pets they buy for. Those profiles could feed analytics, the shopkeeper agent
and a loyalty programme. They are also profiling under the GDPR, so what is built, from what, and for whom matters.
(This is a design position, not legal advice; a privacy lawyer should review it before a real merchant uses it.)

## Decision

A new view, **Customers**, with the rules below.

1. **Observed traits, not inferences about the person.** Each trait is a share of the lines a customer bought,
   counted the same way for everyone: on offer (`mostly` / `sometimes` / `rarely`, the cut points of the action table's
   `offer_buyer`), the cheaper half of their category (value-leaning / mixed / premium-leaning), and the rating of what
   they pick against their category's average. Pets are the pets of the products they buy for. A diet is the diet tag of the
   pet food they bought, after two lines of it. Nothing about health, religion, ethnicity or the like is read or
   guessed, and the test names the allowed fields.
2. **Only for customers who consented.** `consent_behavioural` (ADR 0044) decides: a customer without it is counted and
   not profiled. A customer with fewer than three purchased lines has "too few purchases", not a guess.
3. **Segments carry their evidence.** Each segment shows customers, share, churn rate and average spend; a segment under
   30 customers is faded.
4. **Who responds to what.** For each segment (offer buyers, last order, earlier emails, tracking consent, order size, open
   issue) and each action, the change in the share who ordered within 30 days against no action in the same segment, with
   its 95 % margin. A lift inside its margin is shown grey, a cell under 30 rows is blank: no result is claimed from noise.
5. **Revenue per profile.** Each segment shows the sum of its customers' orders (lifetime and the last 12 months) and its share of all
   profiled customers' revenue. Pets and diets overlap, so their shares add up to more than 100 %.
6. **Relations.** Among customers with one trait, how many more points have another trait than those without it, for the three
   ways of shopping and the pets. Diet tags are left out of relations and preferences: a diet belongs to a kind of pet, so it would
   only show the catalogue.
7. **What each group buys.** For each way of shopping, within dog owners and cat owners separately (so pets do not confound),
   the categories, brands and products more of the group bought than the others, by customers reached. Relations and items use a
   99.7 % margin because hundreds are compared; at product level most differences are hints, and the view says so.
8. **Use.** Profiles choose which offer or message a customer sees. They are never used to set what price a customer pays.

## Aito usage

None in this slice: the traits and rates are counts over the release's fixtures, stored by `./do customer-profiles`
(`data/customer_profiles/`) and checked against the fixtures by a test. The action table those rates come from is the one
Retention's and the Shopkeeper's `_predict purchased_30d` are fitted to (ADR 0051), so the live per-customer predictions and
this table describe the same rows. A next slice replaces the observed rates with Aito `_predict` per segment cell (calibrated,
with `$why`) and adds `_relate` for what separates a segment.

## Acceptance criteria

- [x] A user can see, per trait, the segments with customer count, churn rate and average spend.
- [x] A user can see, for a context field, each action's lift over no action per segment, with its margin and its rows.
- [x] A customer who did not consent has no profile and the lookup says why; the stored profiles hold exactly the consenting customers.
- [x] A profile contains only shopping and pet traits (a test lists the allowed fields).
- [x] A cell with fewer than 30 rows has no lift, and a lift inside its margin is not called a result.
- [x] The planted discount effect (A2) shows: a discount lifts customers who buy mostly on offer, and not those who rarely do.
- [x] Stored profiles that no longer match the fixtures or the release fail a test.
- [x] A user can see revenue per segment, with its share and the last 12 months.
- [x] A user can see how a trait relates to the others, each with its margin; a group under 30 customers has no relation.
- [x] A user can see what a way of shopping buys over-proportionally within a pet group, with the margin.
- [ ] Aito `_predict` per segment cell with `$why` (next slice).

## Demo impact

A new view under Run the shop; no existing demo moment changes. A line in the demo script can point from Retention to it.

## Out of scope

- Inferring anything about the person that the purchases do not show; human diets; any special-category data.
- Personalised prices.
- Real loyalty offers, a customer-facing profile page and consent management (later slices).
- Claiming a segment "is price sensitive": the view says what they bought, and separately what they responded to.

## Consequences

**Good:** every figure has its rows and its margin; the consent rule and the allowed traits are tested.
**Bad:** observed rates are descriptive, not causal, and wide for small segments; the action table is simulated, so the
effects shown are those it was generated with.
