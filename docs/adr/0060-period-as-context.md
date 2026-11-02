# ADR 0060: The period as context in Analytics: figures, preferences, similar segments and feedback modelled within the window

**Status:** Accepted in part (2026-11-02, Antti: "you can do those in the order you prefer"). Built: with only a period picked, Preferences and Other segments compare the period with the one before it; the preference backtest (docs/verification/period-context.md) says history predicts as well as a window, so a window is shown as a description, not as the default. Not built: the rest of the views and the funnel for a segment and a window. Proposed 2026-11-02, Antti: "including the temporal span and its context in the analytics and data views... if it performs well enough. E.g. the funnel would be modeled to the temporal window AND segment within the temporal context, preferences, similar segments, feedback etc. would be modeled similarly."
**Date:** 2026-11-02
**Deciders:** Antti

## Context

Analytics lets the reader pick a period (ADR 0055). Today the period does two things: it sets the selection's headline figures against the same number of months before
it, and it narrows the raw-data widget. The rest of the view ignores it: Preferences, Other segments, Acquisition, Actions and Feedback are always computed over all months
in the data, and the Product view's funnel is per month for one product, with no segment. So a reader who asks "what did value-leaning customers prefer in the last
three months" is shown what they preferred over two years.

Two things are not known and decide how far to go:
- Whether a window's statistics say more about what happens next than all of history does. In this simulated data, much is generated from stable rules (the demand
  evaluation of ADR 0014 found nothing for a model to learn beyond "same as last month"), so a window can be *noisier* and no better. A real shop's data may differ.
- Whether Aito's own queries (`_predict`, `_relate`, `_estimate`) conditioned on a month range behave well on a segment of a few hundred customers.

## Decision

Treat the period as one more condition on every figure the Analytics view shows, **if a measured check says it earns its place**, view by view:

1. **A backtest first, per view.** For each view (preferences, related segments, acquisition, actions, feedback), compare two ways of predicting the *next* period for a
   segment: from the window (the last N months) and from all earlier months. Time-split, train on months before each test month only (not "every other month":
   that leaks the future and flatters the model, as the first demand experiment did). A view gets the window when it predicts the next period at least as well, with an
   interval; otherwise it keeps all history and says so.
2. **The window is shown, not assumed.** Each tab names the months it covers and how many customers and rows that is; a window too small to compare says "Too few
   customers in this window" rather than showing noise (the same rule as MIN_GROUP).
3. **The Product funnel for a segment and a window** (the example in the request): the funnel's impressions, clicks and purchases are estimated for the product *within
   a segment and a window*, conditioned on the segment's traits and the months. It needs the segment to be expressible as `where` conditions on the funnel's tables; where it is not
   (traits that exist only in the stored profile facts), the funnel says "not available for this segment" and does not approximate.
4. **Compare, don't replace:** the window's number is shown beside the all-history number with the Pattern? label (ADR 0055) for the difference, so a reader sees what the
   window changes.

## Aito usage

Queries conditioned on a month range (`{"month": {"$gte": start, "$lte": end}}`) with `_predict`, `_relate` and `_estimate`; each pattern is run against the data and its response shape checked
before it is built on, and added to `docs/aito-cheatsheet.md` and `./do aito-check` (project rules for any new query pattern). Not decided here: whether the per-customer facts
in `data/customer_profiles/facts.json` become per-month facts, or the views read the order tables directly. That is the first thing the backtest has to settle.

## Acceptance criteria

- [ ] A backtest report (`docs/verification/period-context.md`) for each view: window against all history, time-split, with intervals, and the decision per view stated.
- [ ] A view that uses the window says which months and how many customers; a window below the minimum says so instead of showing figures.
- [ ] With a period picked, a view the backtest did not support shows all-history figures and says "all months".
- [ ] The Product funnel for a segment and a window matches the same funnel computed by counting the window's rows, within the interval the page states.
- [ ] No view silently falls back: every fallback is a visible sentence.

## Demo impact

`docs/demo-script.md`: the Analytics walk-through gains the window; wording stays honest where the backtest finds the window adds nothing.

## Out of scope

Forecasting a segment's next period (this decides what to *show*, not a new prediction product); changing the data generator to make windows matter; the web-journey path idea
(`docs/notes`, not built); anything the shop would do automatically with the result.
