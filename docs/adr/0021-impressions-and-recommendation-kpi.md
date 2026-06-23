# ADR 0021 — Impressions table and a real recommendation KPI

**Status:** Proposed
**Date:** 2026-06-23
**Deciders:** Antti

## Context

Every recommendation surface in this demo (Smart Search, For You) ranks
products with a `_recommend` whose `goal` is `{ customer_segment }`:

```json
{ "from": "order_lines", "recommend": "product_sku",
  "goal": { "customer_segment": "dog_owner" } }
```

This is a *segment-affinity* rank — `P(segment | product)` — used as a
proxy for purchase propensity. It works, but it is a workaround, forced
by a gap in the data model: **we have no impressions table.**
`order_lines` records only purchases (positive events). There is no
negative class, so there is nothing to learn a `P(purchase)` from, and
the one outcome field we do have (`returned`) is uniform at ~3% — a
`goal: { returned: false }` collapses to baseline (see ADR 0006 and
`docs/aito-cheatsheet.md`).

The canonical reference demo (`aito-demo`, the grocery store) does this
the textbook way. *All* of its recommendation and search features query
a single `impressions` table:

```json
"impressions": { "type": "table", "columns": {
  "session":  { "type": "String",  "link": "sessions.id" },
  "product":  { "type": "String",  "link": "products.id" },
  "purchase": { "type": "Boolean" }
}}
```

…and recommend with `goal: { purchase: true }`. Each row is "a product
was shown in a session, and here's whether it was bought" — the clean
conversion KPI our demo lacks. An evaluator who knows Aito will look for
exactly this shape and notice its absence.

## Decision

Add a **multi-KPI `impressions` table** — richer than the reference
demo's single `purchase` boolean — and re-point the recommendation
surfaces to learn from it.

### New `impressions` table

One row per product shown to a customer in a browsing context, with the
funnel outcome recorded. A *view* is implicit (every row is a view); the
three booleans capture the funnel beyond it.

| Column | Type | Purpose |
|---|---|---|
| `impression_id` | String | primary |
| `session_id` | String | groups impressions shown together (no `sessions` table — grouping key only) |
| `customer_id` | String (link → customers.customer_id) | who saw it |
| `product_sku` | String (link → products.sku) | what was shown |
| `surface` | String | `search` \| `for_you` \| `category` \| `bought_together` |
| `search_query` | Text | the query string when `surface = search`; `""` otherwise |
| `position` | Int | rank position in the shown list (0-based) |
| `month` | String | YYYY-MM (categorical, like `orders.month`) |
| `customer_segment / pet_size / lifestyle / health_focus / treat_affinity / brand_loyalty` | String | **denormalised** customer context — single-hop conditioning, same rationale as `order_lines` (ADR 0006/0017) |
| `product_pet_type / category / brand` | String | denormalised product context for `basedOn` priors |
| **`clicked`** | Boolean | the impression was clicked |
| **`added_to_cart`** | Boolean | clicked → added to cart |
| **`purchased`** | Boolean | the conversion KPI |

**Funnel monotonicity invariant:** `purchased ⇒ added_to_cart ⇒
clicked`. The fixture generator enforces this; `aito-check` asserts it.

### Fixture generation

Reuse the existing affinity machinery — `_customer_product_score`,
`_category_bias_for_customer`, the per-persona brand/dietary
correlations — so the learnable signal is *consistent with the
purchases already in `order_lines`* and with the Smart Search / For You
personas. For each customer's browsing sessions:

- Draw shown products: a mix of affinity-relevant (high score) and
  filler (catalog-random) SKUs, so there is genuine variance to rank on.
- Convert down the funnel with affinity-driven rates, e.g. base
  `click ≈ 0.18`, `cart | click ≈ 0.45`, `purchase | cart ≈ 0.55`,
  each scaled by the customer↔product affinity score and `lifestyle`
  (premium converts higher), clipped to sane bounds.
- Tie purchased impressions to the existing orders where possible so the
  two tables tell one story.

Target ~150 k impressions (≈ overall 12–15% purchase rate). Sized to
stay well inside the shared instance's working set (see
`docs/notes/aito-perf-findings.md` on slice eviction).

### Re-pointed recommendation surfaces

Smart Search (ADR 0006) and For You (ADR 0007) move the persona signal
from `goal` into `where`, and adopt the real KPI as the goal:

```json
{ "from": "impressions",
  "where": {
    "surface": "search",
    "search_query": { "$match": "food" },
    "customer_segment": "dog_owner",
    "customer_pet_size": "small"
  },
  "recommend": "product_sku",
  "goal":      { "purchased": true },
  "basedOn":   ["pet_type", "category", "brand"],
  "limit":     10 }
```

For You drops the `search_query` / `surface` constraints and conditions
on the persona profile alone, goal `{ purchased: true }`.

## Aito usage

- **`_recommend product_sku from impressions`, `goal: { purchased: true }`** —
  the textbook purchase-probability rank. Swap to `goal: { clicked: true }`
  to rank by engagement instead of conversion (the new demo beat).
- **`_predict purchased` / `_predict clicked`** — calibrated absolute
  funnel rates for a (customer × product × context) cell (the
  `_recommend` `$p` is normalised against goal-positives; `_predict`
  gives the absolute number — same distinction we documented for
  Winback).
- **`_relate` / `_evaluate`** over the funnel booleans — e.g. which
  contexts lift `purchased | clicked`, and how accurately Aito predicts
  `purchased` held-out.

All shapes get a worked example in `docs/aito-cheatsheet.md` and a
`./do aito-check` assertion in the same PR (CLAUDE.md §Aito query
sanity). No shape lands in `src/` before it's verified live.

## Acceptance criteria

- [ ] When the impressions fixture loads, the funnel is monotone
  (`purchased ⇒ added_to_cart ⇒ clicked`) for every row, and overall
  rates are sane (click > cart > purchase, none degenerate).
- [ ] A user querying `_recommend … goal: { purchased: true }` for a
  dog-owner persona gets dog-appropriate products ranked top; the same
  query with `goal: { clicked: true }` returns a **visibly different**
  ranking.
- [ ] Smart Search and For You produce the same per-persona flips they
  do today (Maija → cat, Saara → dog), now via a purchase KPI rather
  than segment affinity — re-validated, not assumed.
- [ ] `./do aito-check` asserts: recommend non-empty for known-good
  personas, all `$p ∈ [0,1]`, funnel monotonicity, and `_predict
  purchased` returns both classes.

## Demo impact

- **New beat:** "optimise for clicks vs purchases." Flip `goal` between
  `{ clicked: true }` and `{ purchased: true }` live and watch the
  ranking reorder — engagement-bait vs revenue. Even `aito-demo` can't
  show this; it has only a single `purchase` boolean.
- Smart Search / For You narration becomes the standard, recognisable
  recommendation story ("rank by probability the customer buys"),
  matching what an Aito-literate evaluator expects.
- `docs/demo-script.md` updated for the re-pointed queries and the new
  goal-flip beat. The persona flips themselves are preserved.

## Out of scope

- **Real clickstream ingestion / a `sessions` table.** `session_id` is a
  grouping key, not a modelled entity. No event pipeline.
- **Multi-touch attribution / time-decay of impressions.** Each row is
  an independent shown-product with its funnel outcome.
- **Removing `order_lines`.** Bought Together (ADR 0008), Pattern
  Explorer and Purchase Analytics (ADR 0011) still read it. Impressions
  is additive; it changes the *recommendation goal*, not those views.

## Consequences

**Good:**
- Recommendations rank by a real conversion KPI — the textbook Aito
  shape, matching the reference demo, with a richer multi-objective
  twist that's its own demo moment.
- The segment proxy and its caveats (ADR 0006) stop being load-bearing.
- `_predict purchased` gives calibrated, defensible "X% will buy"
  numbers for the panel.

**Bad:**
- Largest fixture table to date (~150 k rows) → generation time and
  instance working-set pressure; sizing and caching must be watched.
- Smart Search / For You flips must be re-validated against the new
  goal — the fixture's funnel correlations have to reproduce them, or
  the personas need re-tuning.
- Two purchase-bearing tables (`order_lines`, `impressions`) must stay
  mutually consistent, or the demo tells two stories.

## Notes

- Reference: `aito-demo` `src/01-recommend.js`, `src/api/recommendations.js`,
  `docs/data-model.md` §"Impressions Table".
- Builds on the denormalisation pattern in ADR 0006 (Smart Search) and
  ADR 0017 (profile traits); mirrors the outcome-label approach of
  ADR 0020 (Winback's `responded`).
- Open question: do we backfill `position` from a deterministic
  affinity sort, or sample it? Position is a strong real-world click
  driver; including it risks Aito learning "position predicts click"
  over content. Lean toward *not* feeding `position` into recommend
  `basedOn`, keeping it descriptive only. Resolve during implementation.
