# ADR 0064: Experiments — variants of a product, and a choice made per person

**Status:** Accepted (2026-11-04, Antti: "Can you implement the adr?"). Slices 1 and 2 built; slice 3 built as what-if controls (serving variants in the Shop is not built). Proposed on 2026-11-04 as: "Let's test this. We will also need some kind of Experiments page to control the A/B testing and person specific optimizations … this doesn't need to be about prices as such (we could have separate personal offers for emails, some special section or something else that is compliant), but it can also be the titles, images, internal product ad overall and such.")
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
3. The controls, and serving a variant in the Shop. Built as what-if controls only (Amendment 3).

## Amendment 1 (2026-11-04): slice 1 as built

- **Additive tables, not a change to `impressions`.** Variants are `experiment_variants`, showings are `experiment_showings` (one row per showing,
  linked to its experiment, product, customer and variant), experiments are `experiments`. The existing impressions, orders and sales are untouched
  (a regeneration leaves every other fixture byte for byte as it was), so this is an additive data release. The cost: a purchase in an experiment showing
  is **not an order line**, and the page says the showings are simulated and apart from the orders (ADR 0045's one source does not cover them).
- **Twelve experiments, one per best-selling product**, kinds in turn (offer, title, image): eight running, two decided after two months (then the winner at
  90 %, the rest still at random), two drafts. Four months of showings (2026-01 to 2026-04), four a month for each consenting customer with the
  product's pet; 141,056 rows.
- **The hidden reactions reuse the customers' own traits** (`data/experiments.py`): offers by discount sensitivity (ADR 0038), titles by health focus,
  images by newness sensitivity. The answer key holds every customer's true chance on each arm (`data/answer_key/experiment_chances.json`).
- **A reaction that differs in sign between people is planted for titles and images too** (×0.6 for a low health focus, ×0.75 for a low newness
  sensitivity). The first draft had ×0.95 and ×1.0 there: no arm was ever worse for anyone, so the plain winner was also best for every shopper and
  choosing per person could not pay. This was changed after seeing that, for the demo to have something to find, and is stated on the page.
- **The signal on a showing is what the shop observes**, not the trait: the source of the customer's first visit for offers and images, the share of
  wellness diets among their lines for titles. For offers the share of lines bought on offer was tried first and predicts the discount sensitivity far
  worse (52 % of its top level are high against 35 %) than the source does (76 % of affiliate visitors against 36 % of the rest), so the source is used. `signal_arm` crosses it with the arm shown, as
  `customer_actions` crosses its context columns with the action.
- `experiment_showings.json` is generated with the rest (about 30 MB), gitignored like the impressions, and regenerated by `./do` when missing.

## Amendment 2 (2026-11-04): slice 2 as built, and what the demo's world says

- `scripts/experiments_evidence.py` writes `data/evidence/experiments.json` (`./do experiments-evidence`): each arm's showings and purchases counted in Aito,
  the difference of the second arm from the control with a 95 % interval, and per kind whether choosing per person pays, on the last month, which a branch
  of master holding the earlier showings had not learned from. The Experiments page (`/experiments`, Operate) reads it; the what-if controls came in slice 3 (Amendment 3).
- **In the demo's world choosing per person does not pay with these signals** (held-out month, 1,500 shoppers and products per kind): titles +1.7 %
  (0.5 to 3.0, a small gain), offers 0 % (Aito chooses the control for everybody, as the plain test does: even the affiliate visitors' offer lift of
  ×1.9 is under the ≈×2 an offer must beat to pay for its margin on the products tested), images −2.2 % (−3.0 to −1.4: six source levels with a thin difference between them
  cost more than they find). A perfect signal would earn 5–12 %. The page says so, with the ceiling, and offers the per-person choice only where the
  interval is above zero and the gain is 3 % or more (`small gain` between).
- Most experiments are `no clear difference` after four months: about 6,000 showings an arm and a purchase rate near 5 % do not separate a 10 %
  difference in profit per showing from luck. EXP-02 (a title) is the clear one and was decided early; a decision taken after two months on a smaller
  count is the kind the page's interval is there to question.

## Amendment 3 (2026-11-04): slice 3 as built, what-if controls

- **The controls are projections, not switches.** The demo reads stored evidence and the Shop serves no experiment arm, so a start, stop or split
  could change nothing real. Instead each experiment with showings gets a "What if" panel: the share of showings on the second arm while testing, the exploration floor once
  a winner is decided, and a guardrail (how much less than the control the second arm may earn). `GET /api/experiments/{id}/plan` (`src/experiment_plan.py`) answers from the counted arms:
  profit a month at that split, with the control for everybody, and with the better arm decided (floor kept on the other); the cost of testing on against deciding now;
  the further months a clear answer needs at that split (normal approximation, stays as measured; none within three years says so); and whether the guardrail would trip
  (the upper end of the difference's interval below minus the limit, so a guardrail needs the data to say the arm is worse).
- **Drafts have no panel** (nothing to project from; the route answers 400). A split, floor or guardrail out of range is refused with the range.
- **Not built: serving variants in the Shop and a real start/stop/decide.** That needs writes (a sandbox branch as in ADR 0043) and simulated showings so the evidence moves. Open.

## Amendment 4 (2026-11-05): data release 5

The three experiment tables ship as data release 5, under the env name `experiments-data` (the env that already holds them: a branch of master plus
`experiments`, `experiment_variants`, `experiment_showings`). `data/release-env.json` names it and counts the tables; the stored customer profiles and shopkeeper runs
were rewritten offline (`./do customer-profiles`, `./do agent-runs`) so they carry the new release name and are not served as stale. Nothing else in the data changed:
every earlier table has the count it had in `release4`. The app does not query the new tables, so this release only matters to what is built on them next (serving
variants in the Shop). As ADR 0035 says, the app answers 503 on data routes until master matches `release-env.json`, so this merges and deploys **together with** the
promote (the aito-azure cutover), not before it.
