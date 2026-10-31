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
   `offer_buyer`), the cheaper half of their category by list price (value-leaning / mixed / premium-leaning; list price, so a discount cannot make a line look cheaper: a first version compared the price paid and showed a circular offer → value relation, found in review), and the rating of what
   they pick against their category's average. Pets are the pets of the products they buy for. A diet is the diet tag of the
   pet food they bought, after two lines of it. Nothing about health, religion, ethnicity or the like is read or
   guessed, and the test names the allowed fields.
2. **Only for customers who consented.** `consent_behavioural` (ADR 0044) decides: a customer without it is counted and
   not profiled. Customers who did not consent are not searchable by name and the lookup returns only their id (the view has no lookup box since 2026-11-01; the API remains). A customer with fewer than three purchased lines has "too few purchases", not a guess.
3. **Segments carry their evidence.** Each segment shows customers, share, churn rate and average spend; a segment under
   30 customers is faded.
4. **What the actions did, per segment.** For each segment and each action in the action table, the change in the share who ordered within
   30 days against no action in the same segment, and the change in estimated profit per row, each with its 95 % margin. A customer's traits
   come from their whole history and apply to every action row of theirs, so this describes the segments as they are now. The margins treat
   rows as independent although one customer can have several, so they are approximate; a cell inside its margin is shown grey, one under
   30 rows is blank, and about one cell in twenty would pass by chance.
5. **A topic tree selects the segment, by any number of conditions at once.** Ticking "premium-leaning", "dog" and "high-margin" describes
   the customers who meet all three (the shopping traits and margin take one value each; pets and diets can be ticked more than once).
   Nothing ticked is every profiled customer. Above the tree, a figure to compare by (customers, purchases, revenue, profit per customer,
   NPS, churn), shown as six tiles: each condition shows what that figure would be for the segment if it were ticked, as a number and a bar, so a dead end or a
   standout shows before it is picked. A selection is counted when asked for, from `data/customer_profiles/facts.json` (per-customer
   facts for the profiled customers, no names), by `GET /api/customer-profiles/segment?c=trait:value&c=...`; a selection under 30 customers
   is given its size and nothing else. Churn is the shop's own rule (no order in the last three months of the data), a status a customer is in (churned or active) and a rate a segment has; its trend applies the same rule to every month. Margin is a customer's basket margin (gross profit over the price paid for what they kept), high
   or low against the median customer's. On top: the segment's name and size, and a "?" that opens where the segment sits in the preference ranking of the variable it is a slice of (offer, price or rating).
   Then the chosen figure's trend over the months, full width, against everyone's shape, and whether the last three months are in decline.
   Below, tabs as in Product: highlights (what to do, only differences larger than their margins, and who the customers are in words), key figures and the showing funnel (impressions, clicks, carts, purchases over the identified sessions of
   its customers), preferences (what it buys), other segments (how it relates to each, with the chosen figure for the customers in both and a button to tick it), channels, what the shop's actions did for it, and what it says in reviews and NPS answers. Profit is the price paid less the unit cost on the lines kept (a returned line earns nothing),
   less the shop's action costs; there is no delivery or payment cost in the data, so it is profit after products and actions, not a full P&L.
   The unit cost is the inventory's current cost per product, applied to two years of sales. Profit per customer carries a 95 % bootstrap interval
   (a few customers earn much of it), and no interval is given under 30 customers. Revenue is the price paid on the lines kept, the same basis as profit and
   margin. The profit distribution (total, per customer and median, the share the top tenth earns, how many lose money) is in the figures tab for everyone. The response table is per segment, in orders and in estimated profit (the 30-day spend at the shop's
   gross margin less the action's cost): a discount that lifts orders can still lose money.
5b. **Preference ranking.** All customers ranked by how much they prefer something (their share of lines on offer, in the cheaper half, in better-rated
   products, in a category or of a brand, over the average share), as a curve in twenty steps and five fifths, with the top fifth over the average and over the
   bottom fifth (undefined when the bottom fifth buys none), and how many of the selected segment each fifth holds.
5c. **Acquisition.** Each profiled customer's first session (found through their visitor id) gives the channel, the landing page type and the
   landing category they arrived by. For a segment the view shows how many more or fewer of it came each way than of the other customers (points, 99.7 % margin),
   and the profit per customer of those who came that way (where 30 or more stand behind it), against everyone who came that way. Only what was known on arrival is
   read: the label for whether a customer became a regular carries the future and stays in the Acquisition view. "Ads" are the paid channels (paid search,
   social, affiliate) in the channel list; the advertised-product level of the product states is not linked to customers yet.
5d. **Revenue per profile.** Each segment shows the sum of its customers' orders (lifetime and the last 12 months) and its share of all
   profiled customers' revenue. Pets and diets overlap, so their shares add up to more than 100 %.
6. **Relations.** Among customers with one trait, how many more points have another trait than those without it, for the three
   ways of shopping and the pets. Diet tags are left out of relations and preferences: a diet belongs to a kind of pet, so it would
   only show the catalogue.
7. **What each group buys.** For each way of shopping, within dog owners and cat owners separately (so pets do not confound),
   the categories, brands and products more of the group bought than the others, by customers reached. Relations and items use a
   99.7 % margin because hundreds are compared; at product level most differences are hints, and the view says so.
8. **Use.** Profiles choose which offer or message a customer sees. They are never used to set what price a customer pays.

## Scope and wording

The profiles are the release's stored data; a request that names a sandbox is answered with them and `scope: release-not-sandbox`, and the page says so. The response table is observed rates from a simulated action table, not proof that an action caused an order.

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
- [x] A user can see every segment in one list with customers, profit per customer, profit and churn, and select one to inspect.
- [x] A user can see profit per customer per segment, against the average, and how many customers lose money.
- [x] A user can see, for a segment, what each action did to orders and to estimated profit, with its margin.
- [x] A user can see where a segment's customers came from (channel, landing page, landing category), against the others, and what they earn per customer.
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
