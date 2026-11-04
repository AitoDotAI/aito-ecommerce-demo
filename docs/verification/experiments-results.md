# Experiments: results of the pre-registered probe

Run 2026-11-04 on env `experiments-probe` (a branch of `master`; four `xp_` tables of its own, master untouched) with
`scripts/experiment_probe.py`, as registered in `experiments-prereg.md`. 1,200 shoppers, 60 products in 3 kinds of experiment,
230,400 showings (arm drawn 50/50), the last 2 sessions of 24 held out, 1,200 held-out (shopper, product) pairs scored. Every policy is
scored by expected profit per showing from the generator's **true** purchase chances. Raw numbers: `data/evidence/experiment-probe.json`.

## Registered result

| Policy | Profit per showing | vs P1 (95 % interval over shoppers) |
|---|---|---|
| P0 control: the control arm everywhere | 0.764 | |
| P1 winner: the arm that is best over all shoppers (a plain A/B test) | 0.843 | |
| **P2-E** `_predict purchased where {customer, variant}` | 0.840 | −0.3 % (−0.006 … +0.0003) |
| **P2-R** `_recommend variant where {customer, variant.sku}` | 0.819 | −2.8 % (−0.036 … −0.013) |
| P3 oracle: the true best arm per shopper | 0.891 | +5.8 % |

**The decision rule's answer: no.** Neither registered query beats the plain A/B test, so by the rule the Experiments page ships with the
A/B test and "choose per person" is reported as not earning its place *with these queries*. Predictions: P1 beating P0 was right (+10 %,
mostly from free title and image arms); P2 beating P1 was wrong; E closer to the truth than R was right (calibration error 0.049 against
0.064; R also ranks worse).

## Why, and what was tried after (post hoc, labelled as such)

`customer` and `variant` are two separate pieces of evidence for `_predict`, and Aito multiplies what each says: the customer's usual chance
times the variant's lift. That model has **no interaction**, so "this shopper reacts to offers" cannot be expressed: every shopper gets the
same arm order and P2 collapses to P1. An interaction needs one key that holds both, a signal about the shopper and the arm shown
(`lean_arm = "hi|offer"`), which then learns from every shopper with that signal at once.

| Signal in the key (post hoc) | Profit per showing | vs P1 | Share of the P1-to-oracle gap |
|---|---|---|---|
| E2: the shopper's own lean, from their training showings (about 3 purchases per arm: noisy) | 0.847 | +0.6 % (−0.005 … +0.016) | 10 % |
| E3: the same plus the shopper | 0.846 | +0.4 % | 7 % |
| E5, diagnostic: an observable proxy that is right 70 % of the time | 0.875 | **+3.9 %** (+0.025 … +0.040) | 67 % |
| E4, diagnostic: the hidden trait itself, which no shop sees | 0.891 | +5.8 % (+0.042 … +0.056) | 99 % |

So **Aito learns the interaction almost perfectly when the key carries it**; what limits the gain is how well the shop's observable signal
predicts who reacts. A shopper's own few purchases are too thin (10 % of the gap); a signal right 70 % of the time clears the 3 % bar
(67 % of the gap). The diagnostics E4 and E5 use planted truth and are bounds, not results a shop could reproduce.

## What this means for the demo

- Build the variants and the plain A/B test first: it is where most of the gain is (P0 to P1: +10 %).
- Choose per person by a **joint key of an observed signal and the arm**, never by `customer` plus the variant. The signal has to come from
  data the shop has: the shop's whole history (purchases on offer across all products, price band of baskets, loyalty), not one experiment.
- Report the gain of choosing per person against the plain winner with its interval, and switch it on only where the interval is above zero.
- Caveats: one synthetic world, one seed; the lifts are the planted ones (offer ×2.6 / 1.4 / 1.05 by discount sensitivity, title ×1.5 / 0.95,
  image ×1.4 / 1.0); P1 here is learned from 211,200 showings, a smaller experiment would decide worse.
