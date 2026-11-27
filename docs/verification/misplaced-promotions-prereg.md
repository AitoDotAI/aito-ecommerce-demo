# Pre-registration: misplaced promotions (planted effect M1)

Written 2026-11-27, **before** the generator was changed for M1 and before
any generation with it. Every metric, seed and threshold below is fixed now.
The generator is not re-tuned against these checks after seeing them; if it
has to change, this file is amended first, dated, with the reason.

**Why.** Antti 2026-11-27: the pet store should be actionable, "there are
cases were you want discounts and we're the discounts are misplaced". Until
now every promotion lifts demand (P6 shopper odds, the ranker's offer
placement, the offer landing page), so a margin view of the generated shop can
only ever list noise as "sold no more on discount". The mispriced SKUs
(ADR 0027, list price too high) stay the case where a lower price is wanted.

(`D1`–`D3` are already ADR 0062's demand-dynamics switches, so this effect is
`M1`.)

## The planted effect

- **M1, misplaced promotions** (`planted_switches.ON["M1"]`, on in the
  committed fixtures once merged): 15 SKUs (`N_MISPLACED`) are drawn from the
  SKUs that `plan_promotions` puts on offer in at least 3 months of the window
  (`MISPLACED_MIN_MONTHS`) and that are not mispriced, sorted by SKU, sampled
  with their own RNG `stream(seed, "M1")`. The promotion calendar, the
  elasticities and every other draw are unchanged.
- For these SKUs the discount is **still given** (the price paid is the
  discounted one, so the margin is lost), but it moves **nothing**: a
  shopper's odds (P6, click and purchase), the ranker's offer placement and
  the offer landing page see the product as if it were at full price. A real
  shop has such promotions: a price cut its buyers don't respond to, on a
  product the promotion doesn't reach.
- The answer key gains `data/answer_key/misplaced_promotions.json` (the SKUs);
  Aito never sees it.

## Checks

Seeds **42, 7, 99** and the fresh **5113, 6007, 8191** (never used by this
repo's checks). *Pooled* means over all six seeds together.

**M1-0, the switch is the only change (absolute).** With `ON["M1"] = False`,
the generator on this branch writes the same bytes as `origin/main` at
a9361ab for every file it writes (all 24, including the git-ignored
`impressions.json`, `contexts.json`, `experiment_showings.json`), on seeds 42
and 7.

The next checks read the planted generation's `monthly_sales` and
`product_states`, over the **last 8 months** of each seed, and compute a
product-month's **share ratio** exactly as the Shopify app's Margin watch does
(aito-shopify `computeMargin`, `margin-page.js`): its share of the shop's units
that month over its pooled share in its full-price months among the 12 before;
**comparable** when it has a full-price month there and at least 10 units
(`MIN_CELL`) both in the month and in its baseline. *Controls* are the month's
comparable full-price product-months.

| id | what | pass |
|---|---|---|
| M1-a | geometric mean share ratio of the misplaced SKUs' comparable offer product-months ÷ that of the controls, pooled | within [0.9, 1.1] |
| M1-b | the same for every other comparable offer product-month (the working promotions) ÷ controls, pooled | ≥ 1.2 |

**Margin watch on the new data.** The certainty rule of aito-shopify PR #396
as it stands at f0306a7 (each offer product-month judged against that month's
full-price controls by rank; `certaintyNull` / `certaintyOf` in
`margin-watch.js`), run by `scripts/check-certainty-null.mjs` with the answer
key splitting misplaced from working. Rates are of judged offer
product-months, pooled. #396's own bar form is still Antti's decision; these
bars are about this data, not about #396.

| id | what | pass |
|---|---|---|
| MW-1 | misplaced: "Sure (higher)" | ≤ 5 % |
| MW-2 | misplaced: "Sure or Likely (higher)" (nominal 10 %, one-sided) | ≤ 15 % |
| MW-3 | working minus misplaced, "Sure or Likely (higher)" | ≥ 5 percentage points |

A failed check is reported as failed, with its numbers; nothing is moved.

## Who else is affected

aito-core's benches pin this repo at ce14ff2 and 45067d5 and are unaffected.
Once merged, every fresh generation from this repo carries M1. Regenerating
the Cartman demo data and loading it into the shared env are Antti's steps.
