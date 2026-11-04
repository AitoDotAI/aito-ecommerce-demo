# Experiments: variants of a product, and the choice made per person (pre-registration)

Registered 2026-11-04, before any run. Script: `scripts/experiment_probe.py`. It writes only to its own env
(`experiments-probe`, a branch of `master`) and only with `--apply`; the default is a dry run that generates
the data and prints the oracle numbers, which need no Aito.

## Question

A product can be shown in more than one variant: its price or offer, its title, its image, its place in the
shop. ADR 0064 stores each variant as a `product_states`-like row that an impression links to, and shows a
shopper one variant chosen at random while the experiment learns. Can Aito then choose the variant **for each
person**, by expected profit (chance of purchase × margin of that variant), better than choosing one
variant for everybody?

## Data (synthetic, planted answer)

- 1,200 shoppers, each with hidden sensitivities that Aito never reads: to a discount (low, mid, high), to a
  health-focused title, to a lifestyle image. Aito sees only what a shop sees: who was shown what, and whether
  they bought.
- 60 products with a cost; each is in one experiment of two arms: **offer** (list price vs 15 % off),
  **title** (plain vs benefit-led) or **image** (pack shot vs lifestyle). 20 products per kind.
- 192 showings per shopper over 24 sessions (8 a session; 230,400 in all); the arm shown is drawn 50/50 (the exploration the live
  system keeps as a floor). The last two sessions are held out: they are not loaded into Aito. (First drafted as 1,500 shoppers and
  8 sessions; changed before any run because a shopper then had about three purchases on an offer arm, too few for any method to
  tell a discount-sensitive shopper, which would test the data, not Aito.)
- The true chance of a purchase for any shopper, product and arm is known to the generator, so every policy is
  scored by **expected profit per showing** from the true chances, not from noisy outcomes.

## Policies compared (on the held-out showings)

| Policy | Chooses |
|---|---|
| **P0 control** | the control arm of every product |
| **P1 winner** | per product, the arm with the higher expected profit **over all shoppers** (what a plain A/B test decides) |
| **P2 Aito** | per shopper and product, the arm with the higher `P(purchase | shopper, product, arm)` × margin of the arm |
| **P3 oracle** | per shopper and product, the arm with the higher true expected profit (the ceiling) |

Aito's `P(purchase)` is read two ways, reported side by side: **R**, `_recommend` over the variant with the
product's variants as candidates and `goal {purchased: true}`; **E**, `_predict purchased` once per arm with
`where {customer, product, arm}`. ADR 0043 found `_recommend product_state` tying and calibrating worse, and
that a state with no impressions scores near zero; here every arm has impressions by design, and E needs no
ranking across states at all.

## Predictions

- **P1 gains little over P0 or loses**: a discount that raises purchases 1.4× on average costs a 15 % price cut
  to a margin of about a third, so on average it loses; the winner is mostly "control".
- **P2 gains more than P1** because the discount pays only for the high-sensitivity shoppers (planted ×2.5
  against ×1.1); the title and image arms are free, so they pay wherever the lift is above 1.
- **E is closer to the truth than R**, for the reason ADR 0043 gave.
- Per-shopper history is thin (about 170 showings in the training data, about 3–4 purchases on the offer arm): P2 will not reach the
  oracle. I expect it to capture roughly **a third to a half** of the gap between P1 and P3.

## Decision rule

Personalised choice is worth building into the demo (an Experiments page with a "choose per person" switch) only if,
for E or R, **P2 beats P1 on expected profit per showing by at least 3 %** and its 95 % bootstrap interval over
shoppers is above zero. If it captures under a fifth of the P1-to-P3 gap, the page ships with the plain A/B
test (P1) and the per-person choice is reported as not yet earning its place. Strata (offer, title, image) are
reported, not judged.
