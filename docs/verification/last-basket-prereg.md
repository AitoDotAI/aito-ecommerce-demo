# Does the previous order's basket improve the Shop's ranking? (pre-registration)

**Written 2026-10-25, before any run.** Antti: the Shop's cold start could use the customer's latest
basket as context: it gives the pets, and an idea of the shopper's state (the first items for a terrarium,
or a new puppy's second week). Script: `scripts/last_basket_sweep.py`. The experiment is the Shop's
"Start from their last order" option (PR #99), which puts the last order's words in the query as cart words.

## Question

For an identified customer with an earlier order, does adding that order's basket words to the Shop's
"Picked for you" query raise hit@12 and keep the shown percentages calibrated?

## Why not `_evaluate predict`

Tried first, and it can't answer this. In `_predict`, each condition's lift is independent of the
candidate: the pets lift is ×0.824 for the hideout and for any other product (probed 2026-10-25, env
release2). `_recommend` conditions each context lift on the candidate (`hitPropositionLift`'s factors),
which is the cage-in-the-last-basket → hideout interaction this is about. `_evaluate recommend` isn't
available on collections ("not yet available on collections"). So the test is a per-session `_recommend`
sweep.

## Design

- **Sessions:** every ranked session of an identified customer with an order in an earlier month and a
  purchase in the session, since 2025-05: **3,880 sessions, 1,383 customers, 402 in households with a pet
  other than dog or cat** (from the fixtures; `--sessions N` for a pilot).
- **Variants** (the Shop's "Picked for you" query, observable-data-prereg.md's K+, as the Shop sends it):
  - **A:** declared pets (else the pets of earlier orders) as `context.customer.pets`, the month,
    the session's own cart words, `just_bought: false`, the diet rule, the declared-pets candidate filter.
  - **B:** A with the **last order's words added** to the cart words. The last order is the customer's
    orders of their latest earlier month; its words are `basket_words` of its products.
- **Held out by branches, not nested `from`:** customers fall into 5 folds by a hash of their id. For
  each fold the script makes a copy-on-write branch of `release2`, deletes the fold's sessions'
  impressions **on the branch**, ranks each held-out session with plain `_recommend` queries, and deletes
  the branch. A nested `from` per session builds a population copy each (core, td-20261024151214916465).
  `release2` and master are never written. The delete is unmeasured at this size; the first fold is
  timed.
- **Metrics:** hit@12 (a product bought in the session is in the top 12), and the Brier score of `$p`
  over the products the session showed that the Shop could show (the cart's items and rule-breaking food
  aside), as in the R1/R2 sweeps. Paired by session, 95 % interval by normal approximation.

## Predictions, written first

- **A gain in households with a pet other than dog or cat** (n = 402). The data plants a kit
  progression (the next item after a cage and a bottle, K1a ×2.1–3.5 by seed), and the last basket
  carries the owned kit.
- **A tie for dog and cat households** (n = 3,478): nothing is planted that the last basket would
  carry beyond what the pets and cart words already say.
- **No claim about the combined gain.** It is a weighted mix of the two.

## Decision rule

The Shop sends the last order's words by default, for identified customers with an earlier order, if
**both**: the paired hit@12 interval for B − A over all sessions has a lower bound above 0, and the Brier
change B − A is at most +0.01 (the R1/R2 rule). The strata are reported and not judged separately: a gain
only in the 402 would be an argument for a narrower default, to be registered before another run.
The sample is all eligible sessions, fixed above; there is no peeking at a subset.

## Caveats set in advance

- The sessions' own carts are in the query as in the earlier sweeps, so this measures the last order
  **in addition to** the cart, not instead of it.
- Months are the data's resolution: an order earlier in the same month as the session isn't "earlier".
- Synthetic data with planted effects: this shows whether the method finds what was planted and whether
  the query form carries it, not how much a real shop would gain.

## Results

**Pilot, 2026-10-25 (100 sessions, 96 customers, 9 in households with a pet other than dog or cat; not
a decision, the full set above is).** The script ran end to end on 5 throwaway branches, which it
deleted (none left). Two fixes came out of it: `_delete` takes `$in`, not `$or`, on a column; and the
Brier set must also leave out other pets' products, which the candidate filter removes.

| | hit@12 | Brier |
|:--|--:|--:|
| A, the Shop today | 0.150 | 0.1462 |
| B, + last order | 0.140 | 0.1436 |
| B − A, all (n = 100) | −0.010 [−0.054, +0.034] | −0.0026 [−0.0249, +0.0197] |
| B − A, dog/cat (n = 91) | −0.011 [−0.059, +0.037] | −0.0045 [−0.0292, +0.0202] |
| B − A, other pets (n = 9) | 0.000 | +0.0139 [−0.0070, +0.0347] |

Underpowered by design (the intervals are ±0.05; earlier sweeps needed n ≈ 1,400 to resolve ±0.02, and the
kit stratum has 9 sessions here against 402 in the full set), so it says only that the machinery works
and that nothing large shows up. The full set is still to run.

**Full run, 2026-10-25 (all 3,880 eligible sessions, 1,383 customers, 5 folds by customer, 5 throwaway
branches of `release2`, none left).**

| | hit@12 | Brier |
|:--|--:|--:|
| A, the Shop today | 0.135 | 0.1516 |
| B, + last order's words as cart words | 0.122 | 0.1609 |
| **B − A, all (n = 3,880)** | **−0.012 [−0.019, −0.005]** | **+0.0094 [+0.0072, +0.0115]** |
| B − A, dog and cat only (n = 3,478) | −0.014 [−0.021, −0.006] | +0.0098 [+0.0076, +0.0120] |
| B − A, a pet other than dog or cat (n = 402) | +0.000 [−0.020, +0.020] | +0.0047 [−0.0036, +0.0130] |

**Under the rule: B is not adopted.** The hit@12 interval lies below 0 (a loss, not a tie), and Brier is
worse, by 0.0094, inside the +0.01 allowance but with an interval that excludes 0. **The prediction was
wrong on both counts:** no gain for the kit households (a tie, wide), and a loss for dog and cat
households, where I predicted a tie.

**What this does and doesn't say.** It tests one query form: the last order's words placed in the
**cart's** field (`context.basket_categories`). That field learned "this session's cart holds X", so the
last order's words claim something the data never said (a cart that held them), and the loss is
plausibly that mismatch. This is a hypothesis, not tested here. The ADR 0047 path
(`context.last_order.basket_categories`) learns "customers whose last order held X", a different feature
with a different lift (probed 2026-10-25: a different top 3 for the same words), and was not tested. A
fair test of "does the last basket help" needs the path form, on an env with the chained-basket columns
(`scripts/add_chained_baskets.py`), pre-registered as its own variant, **C**, before it runs. The Shop's
"Start from their last order" option (PR #99) is the variant measured here and should not be the default.

## Amendment (2026-10-25, after B's result, before any run of C1 or C2): the path forms

B lost. The hypothesis recorded with it: B put the last order's words in the cart's field, which learned a
different claim. ADR 0047 gives the same history a field of its own, so two variants are registered now,
each against the same control A, on the same 3,880 sessions and folds:

- **C1, the last order by link:** A, with `context.last_order.basket_categories` conditioned on the words
  stored on the session's last order (`{"$and": [{"$match": w}, …]}`). The cart's field is untouched.
- **C2, two orders by link:** C1, plus `context.last_order.previous_order.basket_categories` conditioned on
  the words of the order before it (when there is one; with none, C2 equals C1 for that session).
- **Held out as before** (5 branches of `release2`, the fold's impressions deleted on the branch). Each branch
  first gets the three chained-basket columns in place (`src/chained_baskets.add_columns`, verified on a
  throwaway branch), so `release2` itself is not touched.
- **Predictions:** C1 is a tie for dog and cat households (the pets already say it). C1 is a **gain** for the
  402 households with another pet, where a kit progresses, but I held the same prediction for B and it was
  wrong, so I hold it loosely. C2 adds nothing over C1: a kit progresses one item at a time.
- **Decision rule:** as above, for each of C1 and C2: the hit@12 interval lower bound for the variant minus A
  above 0 over all sessions, and Brier at most +0.01 worse. **Two variants share one control, so each
  interval is 97.5 % (z = 2.24), not 95 %.** If both qualify, the shallower one (C1) is the default: depth is
  only worth adding if C2 beats C1 on the same rule, and that comparison is reported, not judged.
- **Strata** (402 and 3,478) are reported, not judged separately, as before.

## Result of C1 and C2 (2026-10-25, full run, 3,880 held-out sessions, 1,383 customers, 5 folds)

| variant | hit@12 | Brier |
|---|---|---|
| A shop today | 0.135 | 0.1516 |
| C1 last order by link | 0.128 | 0.1660 |
| C2 two orders by link | 0.121 | 0.1736 |

Differences against A (97.5 % intervals, z = 2.24):

| comparison | stratum | n | hit@12 | Brier |
|---|---|---|---|---|
| C1 − A | all | 3,880 | −0.006 [−0.015, +0.003] | +0.0144 [+0.0113, +0.0175] |
| C1 − A | pet other than dog/cat | 402 | +0.000 [−0.026, +0.026] | −0.0001 [−0.0069, +0.0067] |
| C1 − A | dog/cat only | 3,478 | −0.007 [−0.017, +0.003] | +0.0158 [+0.0125, +0.0191] |
| C2 − A | all | 3,880 | −0.013 [−0.024, −0.003] | +0.0220 [+0.0183, +0.0257] |
| C2 − A | pet other than dog/cat | 402 | −0.005 [−0.033, +0.023] | +0.0023 [−0.0050, +0.0096] |
| C2 − A | dog/cat only | 3,478 | −0.014 [−0.026, −0.003] | +0.0239 [+0.0199, +0.0279] |

**Decision under the registered rule: neither qualifies.** The hit@12 lower bound is below 0 for both, and
the Brier of both is more than 0.01 worse than A. Shop's default stays A (pets, no last order). One batch
timed out once and was run again (the retry the sweep has for that).

Against the predictions: the dog/cat tie for C1 was wrong on Brier (+0.016, a real loss) while hit@12 is a
tie; the "gain for other pets" was wrong again (±0.000, interval ±0.026), as it was for B; C2 adding nothing
over C1 held for hit@12 as a direction but C2 is worse than C1 (deeper history costs, it does not help).
The reading that fits all three runs: the pets already say what the last basket would say, and extra
conditions dilute the probabilities (Brier) before they move the ranking (hit@12). The Shop select keeps
the last-order options as an experiment, labelled so; they are not the default.

## Amendment (2026-10-25, after C1 and C2, before any run of C3, C4 or D): ids instead of words

Antti asked whether a bare reference to the last order would do, and whether the customer link and the order
link work together. Registered, each against A, on the same 3,880 sessions:

- **C3, the last order's id only:** A, plus `context.last_order: <order id>`. **Prediction: equal to A.** An
  order is the "last order" of exactly one later session, and that session's impressions are hidden, so the
  id has no rows to learn from (a link id uses only the rows that carry it).
- **D, the customer id:** A, plus `context.customer: <customer id>` (the Shop's "identity" option).
  Prediction: a gain if the customer has other sessions left, none if not.
- **C4, customer id and last order by link:** D, plus the path of C1. Prediction: no better than D, since C1
  lost to A on Brier.
- **Two readings of the folds**, because the customer id needs other rows of the customer to work. *By
  customer* (as before) hides all the customer's ranked sessions: a cold reading, it understates the id.
  *By session* hides only the scored session: the id keeps the customer's other sessions, including later
  ones, which flatters it. The truth lies between; both are reported, neither is judged alone.
- **Decision rule** as before, for each of C3, C4, D against A: hit@12 lower bound above 0 and Brier at most
  +0.01 worse. Three variants share the control, so each interval is 98.3 % (z = 2.39). The rule must hold in
  *both* fold readings for a variant to qualify; C4 is also compared with D (reported, not judged).
