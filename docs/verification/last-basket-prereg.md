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

**Full run:** not run. Run: `PYTHONPATH=. AITO_ENV=release2 python scripts/last_basket_sweep.py --apply`, with
Antti's go-ahead (it writes to throwaway branches on the shared server). A pilot first:
`--sessions 100 --apply`.
