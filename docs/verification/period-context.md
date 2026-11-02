# Verification: the period as context (ADR 0060, step 1: the backtest)

**Run:** 2026-11-02, `uv run python scripts/period_backtest.py` (offline, reads the release 4 fixtures). Repeatable.

## Question

Does a recent window say more about what a segment buys *next* than all earlier months do? Only if so does the Preferences view earn the window as its default.

## Method

Segments: the single-trait segments of at least 100 customers (region, pets, first source: 14). For every origin month with at least 6 months before it and 3 after,
the share of units by category (and by brand) over the 3 months before the origin, and over all months before it, are each set against what the segment bought in the
next 3 months. Distance: total variation between the two share tables. Nothing after the origin is used to predict (a time split; the first demand experiment, which trained on
other months including later ones, flattered the model, and is not used).

## Result

| Preference | Segment-origins | Window minus all history (distance) | Window closer |
|---|---|---|---|
| Category | 224 | +0.0017 ± 0.0032 | 43 % |
| Brand | 224 | +0.0061 ± 0.0028 | 40 % |

Positive means the window is *further* from what happened. Category is a tie; brand is slightly worse with the window. The intervals treat the 224 cases as independent,
and overlapping origins are not: they are optimistic, so the true intervals are wider.

## Reading

- In this simulated data a segment's taste is stable, so history predicts the next months at least as well as a window. By the ADR's gate, **Preferences keep all history as the
  default.**
- That is a statement about *predicting*, not about *describing*. A reader who picks a period asks "what did they buy in these months", which the window answers exactly,
  and where it differs from before is the finding (a recall, a new product). The window's value here is the comparison with the earlier period, not a better forecast.
- Not yet tested: similar segments (`_relate`), Acquisition, Actions and Feedback, nor the funnel for a segment and a window; and whether the per-customer facts need per-month
  versions (here the order lines were read directly, which worked and is cheap offline).
