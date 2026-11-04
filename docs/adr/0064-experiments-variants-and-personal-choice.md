# ADR 0064: Experiments — variants of a product, and a choice made per person

**Status:** Proposed (2026-11-04, Antti: "Let's test this. We will also need some kind of Experiments page to control the A/B testing and person specific optimizations … this doesn't need to be about prices as such (we could have separate personal offers for emails, some special section or something else that is compliant), but it can also be the titles, images, internal product ad overall and such.")
**Date:** 2026-11-04
**Deciders:** Antti
**Builds on:** ADR 0032 (product states), ADR 0038 (labels assigned at random), ADR 0051 (actions and their outcomes, "none" as an action), ADR 0021 (impressions)
**Evidence:** `docs/verification/experiments-prereg.md`, `docs/verification/experiments-results.md`

## Context

A shop does not only choose *which* products to show. It chooses how: the price or an offer, the title, the image, the place or the
ad around the product. ADR 0038 already made two labels random so their effect could be told from the shop's own choices; ADR 0051 made
"no action" a row so an action's effect is not confused with who would have bought anyway. What is missing is the general form: **a product
with competing variants, an experiment that decides between them, and a way to choose per person when one variant is not best for
everyone.**

The probe (`scripts/experiment_probe.py`) tested that on a synthetic shop with planted, person-specific reactions:

- A plain A/B test (the arm that is best over everybody) beat showing the control everywhere by 10 % in profit per showing.
- Choosing per person beat the plain winner by up to 5.8 % (the true ceiling), **but only when Aito's evidence is a key that holds a
  signal about the person together with the arm shown**. Asked as `customer` plus `variant`, it did not beat the plain winner at all:
  `_predict` multiplies the customer's usual chance by the variant's lift and has no interaction. A signal right 70 % of the time
  captured two thirds of the gain; the person's own few purchases captured a tenth.

## Decision

### Variants are rows that an impression links to

A `variants` table, one row per arm of an experiment on a product: `experiment`, `kind` (`offer`, `title`, `image`, `placement`, `ad`),
`arm`, the content that differs (price, offer, title, image reference) and the **margin** of that arm. An impression links to the variant it
showed, next to the product, so the impression log is the experiment log. This is `product_states` generalised: a price or an offer is one
`kind`, the others carry no price.

The arm shown is **drawn at random** per showing, from an allocation the Experiments page sets, with a **floor of exploration**
(10 % by default) that stays after a decision, so every arm keeps impressions in every group and the model keeps learning. Without
random assignment an arm that is shown to people who would buy anyway looks good.

### The value of a variant is expected profit, not the chance of a purchase

`P(purchase | person, product, variant) × margin(variant)`. Ranked by the chance alone, a discount always wins and everything is
discounted; with the margin, a discount is chosen only where the chance rises by more than the margin falls (for a 15 % offer on a product
with a 35 % margin, by more than 1.8 ×). Titles and images cost nothing, so for them the margin is equal and the chance decides.

Aito returns the chance per variant; the margin is applied in the app, which also keeps one variant per product in a list. Neither belongs
in a `_recommend` goal today; a margin-weighted goal or a distinct-by-link option would be a request to the engine, not something this ADR
assumes.

### Choosing per person: a joint key, not `customer` plus `variant`

The evidence for a person is a **key of an observed signal and the arm** (`"hi|offer"`), learned over everyone with that signal.
The signal must come from what the shop has seen of the person across its whole history (purchases on offer, basket price band,
loyalty), and is checked for how well it predicts the reaction before it is used. `customer` as evidence alone is not used for
choosing between arms: it cannot say how a person differs between them.

### The Experiments page

One page, `Experiments`, in the Operate section:

- **List:** each experiment with its hypothesis, kind, arms, allocation and floor, status (`draft`, `running`, `decided`) and
  the number of showings so far.
- **Result of one experiment:** per arm the showings, purchase rate, profit per showing and the difference against the control with
  its interval; the decision (keep running, a winner for everyone, or **choose per person**).
- **Per person:** the signal that was used and how well it predicts the reaction; the estimated gain of choosing per person over the
  plain winner **with its interval**, and the switch is offered only where the interval is above zero.
- **Controls:** start, stop, set the allocation and the exploration floor, decide a winner, with a guardrail that stops an arm whose
  profit per showing falls below the control by more than a set amount.
- **Compliance:** a personal *price* is shown as a personal offer (an email, a coupon, a section of the page), not a different list
  price; titles, images and placement carry no such concern. The page says which kind each experiment is.

## Aito usage

- Per-arm effect and segment differences: `_relate` over the variant given a segment, `_search` counts for the arms.
- Per-person choice: `_predict purchased` where `{signal_arm, product_sku}` for each arm of the product (batched), then the margin in the app.
- Not used for choosing between arms: `_recommend` over the variants (it ranked worse in the probe) and `customer` plus `variant`.

## Acceptance criteria

- A user can create an experiment on a product with two arms of one kind and see, per arm, showings, purchase rate and profit per showing.
- A running experiment shows each arm at its allocation, and an arm keeps showing at the exploration floor after a winner is chosen.
- When the per-person choice is switched on, the page shows its gain over the plain winner with an interval, measured on showings that
  were not used to learn it.
- A list never shows two variants of the same product.
- A personal price is never presented as a list price.

## Demo impact

A new Experiments page in the Operate section and a line in `docs/demo-script.md` after Product: "which title, image or offer, and for whom".

## Out of scope

- Sequential testing and stopping rules beyond a guardrail on profit.
- Multi-armed bandits that change the allocation by themselves (the floor and a manual allocation first).
- Serving variants in the Shop's live ranking (a later slice; the page first reads showings the generator produces).
- Real price personalisation: the demo shows offers, not personalised list prices.

## Build, in slices

1. The generator adds variants and randomised showings to the main data (a data release), with an answer key for the planted reactions.
2. The Experiments page, read-only: the results, the decision and the per-person gain with its interval, from stored files.
3. The controls and serving a variant in the Shop.
