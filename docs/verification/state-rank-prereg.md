# Product state in the Shop's ranking: pre-registration

Registered 2026-10-26, before any run. Script: `scripts/state_rank_sweep.py` (reuses the sessions, folds and
throwaway branches of `scripts/last_basket_sweep.py`). Run only with Antti's go-ahead, since it writes branches
on the shared server.

## Question

The Shop's "Picked for you" is `_recommend product_sku` and does not read the month's product state in its
order (ADR 0043: recommending `product_state` itself tied and calibrated worse). The Shop's gear now offers to
re-score Aito's top 40 by the state, as this app's multiplication of Aito's shop-wide lifts:

- **S1, `offer`:** score = `$p` × lift(this month's offer band) ÷ lift(no offer).
- **S2, `change`:** score = `$p` × lift(offer band now) ÷ lift(last month's band) × lift(stars now) ÷ lift(stars
  last month): only what changed, since `$p` already carries a product's usual state.

Does either rank held-out sessions better than Aito's order alone?

## Design

- **Sessions, folds, branches:** as the last-basket sweeps: 3,880 ranked sessions of identified customers with an
  earlier order and a purchase, since 2025-05; 5 folds by customer; per fold one branch of `release2` with the
  fold's impressions deleted, so the lifts read on the branch never saw the held-out sessions.
- **Control A:** the last-basket sweeps' A (pets filter, the session's cart and month, the diet rule), top 12.
  The Shop's current defaults differ (own history, no season). State re-scoring is tested as an increment on a
  measured base; a follow-up can repeat it on the defaults.
- **S1, S2:** A's top 40 by `$p`, re-scored with the session month's state of each product (known when a list
  is shown, so it is not leakage), top 12 by score.
- **Measures:** hit@12 (a purchased product among the top 12) and Brier over the shown candidates, with a
  re-scored number read as a probability capped at 1.
- **Intervals:** paired, normal approximation over sessions, 97.5 % (two variants share one control, z = 2.24).

## Predictions

- **Offer (S1):** a small gain in hit@12 at best. The lifts are shop-wide, the same for any product, so they
  reorder near-ties; in the live Shop on 2026-10-26 they moved aquarium filters and fish food into a dog
  household's top 8 (p ≈ 0.40 for all, nearly tied). I expect hit@12 not to move or to fall, and **Brier to
  worsen** (×2.2 on a probability that is already calibrated is not calibrated).
- **Change (S2):** nearer to a tie than S1, since most products have no change month to month.

## Decision rule

A variant is adopted into the Shop's defaults only if its hit@12 lower bound against A is above 0 over all
sessions **and** its Brier is at most +0.01 worse. Otherwise it stays an option in the gear, labelled as an
experiment. Strata (a pet other than dog or cat: n ≈ 402; dog and cat: n ≈ 3,478) are reported, not judged.
