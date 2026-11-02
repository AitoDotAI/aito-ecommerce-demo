# ADR 0038: Actionable product states, shoppers who react differently, and a product manager's view

**Status:** Accepted (2026-10-24, Antti: "review, fix and merge all on green")
**Date:** 2026-10-24
**Deciders:** Antti

## Context

ADR 0032 made a product's monthly state a row (`product_states`): price,
list price, discount band, on offer, a star band, new or established, a
rival's launch, a recent price rise. Three of these change behaviour in the
generator, and each through one fixed trait:

- an offer lifts conversion ×2.5 for a budget shopper, ×1.2 for a premium one;
- "new" lifts only shoppers who aren't brand-loyal (×1.6);
- stars lift every shopper the same (5 stars ×1.3, 1–2 stars ×0.8).

That leaves three gaps:

1. **Little the shop can act on.** Price and discount are the only state
   the shop sets. A real shop also decides which products carry a label
   ("Recommended", "Staff pick"), and lives with stock running low.
2. **Shoppers don't differ in what moves them.** Real shoppers do: some
   buy only on offer, some read the stars, some chase what's new. A shop
   wants to know which, and Aito should have to find it out from what each
   shopper did.
3. **No view answers the product manager.** "What will this product's
   click-through be this month, why, and what if I discount it or label
   it?" Pricing answers it for units (ADR 0029), not for clicks or
   conversion, and not for labels or stock.

ADR 0039 (reviews) and ADR 0040 (the acquisition funnel) share this ADR's
data release.

## Decision

### New state columns (`product_states`)

| Column | Values | Set by |
|---|---|---|
| `label` | `none`, `recommended`, `staff_pick`, `popular` | `recommended` and `staff_pick`: the shop, chosen **at random** each month for 5 % of products each, so their effect is identifiable (a natural experiment). `popular`: a visible rule, the top 5 % of last month's units in each category |
| `stock` | `in_stock`, `low` | `low` in a month when the product's stock fell under two weeks of its demand (from `inventory`'s replenishment plan, now monthly) |
| `review_count_band` | `none`, `1-4`, `5-19`, `20+` | from reviews written before the month, as `rating_band` |

Every new column is in the initial schema (ADR 0030: columns added in place
come back typed `Unknown`).

### Shoppers with sensitivities (hidden, as ADR 0033's traits)

Each shopper draws four sensitivities, each `high`, `mid` or `low`:

| Sensitivity | Drawn | Correlated with |
|---|---|---|
| discount | 30 / 45 / 25 % | budget lifestyle: `high` at 2× the rate |
| stars | 30 / 50 / 20 % | high health focus: `high` at 1.5× |
| newness | 20 / 50 / 30 % | flexible brand loyalty: `high` at 2× |
| labels | 25 / 50 / 25 % | none |

They stay in the generator and its answer key (`data/answer_key/`). No
table Aito reads holds them (ADR 0033). The shop sees only what they cause.

### Planted effects (odds on click, cart and purchase of an impression)

These replace ADR 0032's P1 and P4 tables. The aggregate offer and stars
effects stay inside P1's and P4's checked ranges.

| # | Effect | high | mid | low |
|---|---|---|---|---|
| P6 | On offer, by discount sensitivity, ×(1 + k · discount_pct / 10) | k = 1.0 | k = 0.4 | k = 0.1 |
| P7 | Stars, by stars sensitivity: 5 stars / 1–2 stars | ×1.7 / ×0.45 | ×1.25 / ×0.8 | ×1.05 / ×0.95 |
| P8 | New, by newness sensitivity | ×2.2 | ×1.3 | ×0.9 |
| P9 | Label `recommended` / `staff_pick` / `popular`, by label sensitivity | ×1.8 / ×1.6 / ×1.7 | ×1.25 | ×1.0 |
| P10 | Low stock | ×1.25 on purchase only, every shopper ("only a few left") | | |

Each effect draws from its own seeded RNG, and each is judged against a
null generation (the effect off, the same seed), as ADR 0032's are:

- the effect's ratio among `high` shoppers ≥ 1.5× its ratio among `low`, on
  every seed;
- the aggregate offer and stars ratios stay inside P1's and P4's ranges;
- the older checks (D, S, P, K) re-run; a range that moves is changed in
  the diff, with its reason.

Thresholds are written to `docs/verification/actionable-states-prereg.md`
before the generator changes.

### What the shop can see of a sensitivity

ADR 0033 lets a view use features **derived visibly from history**. Each
context gains three, computed as of the context's month from the
shopper's earlier orders and impressions:

- `offer_share`: the share of the shopper's earlier purchases bought on
  offer (`none`, `low`, `high`);
- `new_share`: the same for new products;
- `label_share`: the same for labelled products.

Aito can then use a sensitivity two ways: from the shopper's own rows (the
customer link) or from the derived band. Both are probed (Q8).

### The product manager's view

A new owner's view, **Product manager**: under ADR 0041 it is the levers
of the **Product** view (What if, For whom). Pick a product and a month; see:

1. **Its state** this month: price, discount, label, stock, stars, reviews.
2. **Aito's estimate of its click-through and conversion**, for an
   impression on each surface, with `$why`: the lifts from its own state
   ("on offer ×1.4", "5 stars ×1.2") and from the product.
3. **What if:** change the discount band, the label or the stock (and
   later the price, through the discount), see the estimate move, and see
   which lift changed.
4. **For whom:** the estimate for shoppers with high and low `offer_share`
   (and the other bands). This shows who an offer is wasted on.

**A probability is shown only if it's calibrated.** The estimate's
calibration is checked on held-out months: predicted against observed CTR
in deciles. If it misses by more than the pre-registered tolerance, the
view shows relative change ("×1.4 more clicks than without the offer")
instead of a CTR. The repo has inflated `$p` on record (`_recommend`
saturation), so this guard is in the acceptance criteria.

### Analytics

Shop analytics relates purchases to `label`, `stock` and
`review_count_band`, and to the derived share bands, beside ADR 0032's
state fields.

### The Shop

The Shop keeps recommending `product_sku`. The B5 sweep found product
states tie products on hit@10 and score worse on Brier. States
reach the grid as data (the shopper reacts to them), and the cards show
offers, labels and stock as facts. Explaining their effect is the product
manager's view's job.

## Aito usage, and what to probe first

Each shape is probed on a test env, and its response inspected, before a
view uses it (CLAUDE.md).

| # | Shape | Question |
|---|---|---|
| Q7 | `_predict clicked` (and `purchased`) on `impressions`, `where {product_sku, product_state.discount_band, product_state.label, product_state.stock, context.surface}`, `select ["$p", "$why"]` | Do the state's fields enter the estimate and `$why` as lifts? Is `$p` calibrated on held-out months? |
| Q7b | the same with a state value the product never had (a what-if) | Does `where` on a linked field accept a value with no row for this product, and does the estimate move by that value's lift? |
| Q8 | Q7 plus `context.customer` or `context.offer_share` | Does the offer's lift differ between `high` and `low` discount shoppers (answer key), by either route? |
| Q9 | `_relate purchased` → `product_state.label`, `.stock` on `impressions` | ADR 0032's one-link form, for the new fields |

**Risk on record:** Aito refuses some multi-condition queries with a NaN
error (lifts multiplied past a double; the repro is with Aito core). Q7's
`where` has five conditions. If it hits the refusal, the view waits for
core's fix and we don't work around it; the finding goes to core with a
minimal repro.

## Acceptance criteria

- [ ] P6–P10 pass their pre-registered checks against the null
      generation, on every seed. The older checks pass or move with
      reasons.
- [ ] A user can open the product manager's view, pick a product, and see
      its estimated CTR and conversion with the lifts from its state.
- [ ] A user can set a discount, a label or low stock and see the estimate
      and the changed lift. Removing the change restores the first
      estimate.
- [ ] A user can compare the estimate for shoppers with high and low
      `offer_share`, and for a discount the high group's lift is larger.
- [ ] When the calibration check fails, the view shows relative change,
      not a CTR.
- [ ] Shop analytics lists `label` and `stock` with intervals.

## Demo impact

A new owner beat after the Shop: "This dog food is on 15 % off. Aito
expects it to get ×N more clicks (the number comes from the run), most of
them from shoppers who buy on offer. Here's the same product with a Staff pick label instead,
no discount."

## Out of scope

- Optimising prices or labels (a recommendation of what to set). The view
  explains and simulates; deciding stays with the manager.
- Stock-outs that remove a product from sale.
- Real A/B testing. The random labels are the generator's experiment, not
  an experiment framework.
- Weekly states.

## Consequences

**Good:**
- Every state field a shop controls has a planted, checked effect, and one
  view explains and simulates it.
- Aito has to infer sensitivities from behaviour, which is a fair test of
  personalisation and an Evidence entry (ADR 0037).

**Bad:**
- A full regeneration and reload. The Shop's shoppers are re-picked where
  their stories no longer hold.
- The NaN refusal may block Q7 until core fixes it.

## Plan

1. ADRs 0038–0040 and one pre-registration with every threshold.
2. The generator and schema, with offline checks against null generations.
3. A test env, loaded by Antti at night, then Q7–Q9 and ADRs 0039/0040's
   probes.
4. The views, one PR each. The release goes live with ADR 0035's cutover.


## Notes

### Amendment (2026-10-24): "for whom" (Q8) is not delivered

Acceptance criterion 4 ("compare the estimate for shoppers with high and low
`offer_share`, and for a discount the high group's lift is larger") **is not
met and is not claimed by any view.** Probed on `release2`:

- Putting the shopper (`context.customer` or `context.offer_share`) and the
  band in one `where` makes Aito multiply the shopper's lift by the band's
  lift, so the band's effect comes out the same for everyone: 20+ ÷ none is
  0.885 for `offer_share` high and 0.883 for low, and 0.87–0.88 for four
  customers of both sensitivities.
- Restricting the population to a band-by-share cell separates `none` from the
  others, but the derived `offer_share` does not track the hidden sensitivity
  (high 1.88, low 2.30 on list showings). The answer key says ×2.99, ×1.99 and
  ×1.33 for high, mid and low.

It stays an open research item: a query shape that lets the offer's effect
depend on the shopper, or a better derived band. Q7's state lifts
(`docs/aito-cheatsheet.md`) also need the list population before a view shows
them (ADR 0045, Notes).
