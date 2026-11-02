# ADR 0061: Supply follows what drives demand, and the second lever: ending a line that does not move

**Status:** Proposed. 2026-11-02, Antti: "Related to supply predictions.. We should include the product state and also temporal predictions with supply. E.g. if a new product gets 1-star or 5-star reviews, this should drive both demand and its estimate. If you have products like winter clothes for dogs, christmas calendars or similar seasonal ware, these should be included in estimation. Essentially everything that drives demand, should drive supply." and "we have 2 levers here. Instead of adjusting supply, we can adjust demand... a product that takes inventory or is going bad... and doesn't move [is a] target for ending the product line and selling inventory with discounts."
**Date:** 2026-11-02
**Deciders:** Antti

## Context

Supply's reorder list is observed sales over the last three months (ADR 0045's Supply section); Aito does the overstock markdown. The reason it is not a forecast: Aito's range
forecast did not beat "the same range as last month" (41.0 % against 44.1 % on April). That forecast conditioned on last month's range, the product id and its category, brand,
pet and season. It did **not** include the product's state (its stars, whether it is new, an offer, a rival's launch, its label, its stock), which the generator makes drive demand (ADR 0032:
newness, stars, the season), so the test was not a fair try at "everything that drives demand".

## Evidence (step 1, run 2026-11-02, `scripts/supply_drivers_backtest.py`)

Seven test months (October 2025 to April 2026), each trained only on months before it; accuracy of the sales range, `_evaluate`:

| Conditions | Mean accuracy |
|---|---|
| "Same range as last month" (naive) | 39.4 % |
| Last month's range, season, category | 37.0 % |
| … + the product's stars band and age (new or not), read through the product state | **41.1 %** (above naive in 6 of 7 months) |
| … + on offer, rival launched | 40.2 % |
| … + label, stock, discount band | 40.3 % |

So the drivers carry signal and the first fair model beats the naive rule by about 1.7 points on average; more drivers do not add to it on this measure, which counts only exact ranges.
The earlier "no feature set beats naive" included the state's *id*, which is unique per product-month and carries nothing. A margin of this size needs an interval before it is said
out loud (the page reports one).

## Decision

1. **The forecast gets the drivers.** The Supply forecast and its accuracy test condition on the product's state (stars band, age, offer, rival, label, stock, season, and the month's
   category) alongside last month's range. Seasonal ware (winter clothes, an Advent calendar) is covered by the season and the category; if the catalogue has none, adding a few seasonal products to
   the generator is a separate, explicit data change (a data release), not part of this.
2. **The test is scored fairly and reported with an interval.** A time split, trained on earlier months only; the page says how many months and what the difference against "same as last month" is,
   with its interval. The reorder list moves from observed sales to the model's estimate **only if** the interval clears 0 on a point (unit) forecast, scored by absolute error, not just range
   hits. Otherwise it stays on observed sales and says so.
3. **A product with a driver the shop knows is ahead** (a new product with its first 1-star or 5-star reviews, a season starting) is shown with what moved its estimate (`$why`), so the
   reorder quantity can be read as a reason, not a number.
4. **The second lever: demand.** Supply gains a third list beside "reorder" and "overstock": **candidates to end the line**: products that tie up stock, sell too slowly to clear it even at the
   deepest markdown the page tests (today 14 of the 15 largest overstocked products), and have no driver ahead that would move them (no season coming, no promotion that lifts them). For each:
   the capital and carrying cost, the weeks to clear at the deepest markdown, and the clearance price that moves the stock within a quarter, with the loss against cost stated. The page recommends;
   the shop decides; nothing is sent or changed (as everywhere here).

## Aito usage

`_evaluate` over monthly_sales with linked fields (`product_state.rating_band`, `product_state.age`, ... through the link) and a `$lt` train bound; `_estimate units_sold` conditioned on the same fields for
the point forecast; `_recommend`/`_relate` for what moved it. Linked-field conditions and `$lt` on a train month are new query patterns: both ran against the data (`scripts/supply_drivers_backtest.py`)
and are to be added to `docs/aito-cheatsheet.md` and `./do aito-check` when built.

## Acceptance criteria

- [ ] The accuracy test conditions on the state and season, trains only on earlier months, and the Model checks page shows the difference against the naive rule with its interval.
- [ ] A point forecast scored by absolute error against "same as last month" and against the 3-month mean, with intervals, decides whether the reorder list uses it; the page says which it uses and why.
- [ ] A new product's reorder estimate moves with its stars (a test on the generated data: the same product with 5-star and 1-star reviews gets a different estimate), and the page shows the reason.
- [ ] Supply lists products to end, each with the capital, the weeks to clear at the deepest markdown and the clearance price; a product with a season ahead is not on it.
- [ ] Nothing is silently left out: a product the model cannot estimate is listed as such.

## Demo impact

`docs/demo-script.md` Supply section: the reorder list's source, the new list, and the honest line about the model against the simple rule.

## Out of scope

Real supplier terms, lead-time optimisation beyond the existing reorder point, and any automatic action: ending a line, repricing or ordering is the shop's decision.
