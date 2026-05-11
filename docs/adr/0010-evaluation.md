# ADR 0010: Evaluation — honest pass/fail across four models

**Status:** Accepted
**Date:** 2026-05-11
**Deciders:** Demo team

## Context

`TASK.md` writes Evaluation as:

> Pass/fail rows for each prediction model (recommendations,
> smart search, product filling, return risk) with accuracy
> bands and last-evaluated timestamps. Aito panel shows the
> `_evaluate` endpoint and the evaluation methodology.

And the load-bearing demo moment:

> Evaluation: at least one model deliberately *fails* its
> threshold — the demo is honest, not omnipotent. Sales
> conversation improves when Aito visibly knows it doesn't know.

Live `_evaluate` against PetNord (2026-05-11) confirms the
fixture's signal #5 makes Return Risk a clean honest-failure:

| Model | Accuracy | Baseline | Gain | Verdict |
|---|---|---|---|---|
| Pet-type from name           | 97.5 % | 0.0 %  | +97.5 pp | **pass** |
| Dietary from name+brand+cat. | 71.5 % | 24.5 % | +47.0 pp | **pass** |
| Segment from product attrs   | 80.5 % | 46.5 % | +34.0 pp | **pass** |
| **Return Risk (returned)**   | 96.5 % | 96.5 % | **+0.0 pp** | **FAIL** |

Return Risk's 96.5 % is the share of `returned = false` lines —
Aito learned nothing beyond the prior. That's *the honest failure
case*: a model that looks impressive on the accuracy axis but
adds zero signal vs. always guessing "won't be returned."

## Aito usage

### Live `_evaluate` shape (verified)

```json
POST /api/v1/_evaluate
{
  "testSource": { "from": "<table>", "limit": 200 },
  "evaluate": {
    "from":    "<table>",
    "where":   { "<feature>": { "$get": "<feature>" }, ... },
    "predict": "<target>"
  },
  "select": ["accuracy", "baseAccuracy", "n"]
}
```

- `testSource` defines the held-out rows. Aito picks `limit`
  rows, hides the target, and compares.
- `where` uses Aito's `$get` operator to read each held-out row's
  feature values back into the prediction's conditioning set.
- `select` filters the response. Aito's default response is
  enormous (per-case timings, full feature lists, etc.); we
  keep just the headline numbers.

### Schema additions: none

The four models all read off columns that already exist in the
PetNord DB. No new denormalisation needed for this view.

### `baseAccuracy` quirk

For some predicts (e.g. pet-type from name), Aito returns
`baseAccuracy: 0.0` — which looks wrong vs. the obvious
"majority-class prior" baseline. The behaviour is consistent
across runs and the `accuracyGain` field is still meaningful
(it's `accuracy - baseAccuracy`). The Evaluation view shows
both numbers verbatim; we don't try to "correct" Aito's
baseline calculation in service code. If a reviewer asks, the
honest answer is "this is what Aito returned" and the gain is
still the right pass/fail signal.

## Decision

### Four models, threshold = +10 pp accuracy gain

| Model id | Table | Where | Predict | Pass band |
|---|---|---|---|---|
| `pet_type_from_name` | `products` | `name`, `brand` | `pet_type` | gain ≥ +10 pp |
| `dietary_from_name` | `products` | `name`, `brand`, `category`, `pet_type` | `dietary` | gain ≥ +10 pp |
| `segment_from_product` | `order_lines` | `product_sku.pet_type`, `product_sku.category` | `customer_segment` | gain ≥ +10 pp |
| `return_risk` | `order_lines` | `product_sku.category`, `product_sku.pet_type`, `customer_segment` | `returned` | gain ≥ +10 pp (fails) |

The Return Risk row is the load-bearing failure case. Its
accuracy is high (~96 %) because the prior is high; its gain is
near zero because the features Aito has don't carry signal about
*which* of those 3 % of lines actually get returned. Fixture
signal #5 (~3 % returned share, drawn uniformly across pet types
and segments) is the deliberate setup.

### `/api/evaluation` response

```ts
interface EvalModelResult {
  id: string;
  label: string;            // human-readable model name
  table: string;
  predict: string;
  features: string[];       // labels of the where-fields
  accuracy: number;
  base_accuracy: number;
  accuracy_gain: number;
  n: number;
  threshold_pp: number;     // 10 by default
  verdict: "pass" | "fail";
  last_query: { endpoint: string; body: object };
}

interface EvalResponse {
  models: EvalModelResult[];
  last_run: string;         // ISO timestamp
  total_response_ms: number;
}
```

### Endpoint

`GET /api/evaluation` — runs all four `_evaluate` calls **in
parallel** (each takes 5–15 s live; serial would be ~40 s).
Cached 1 hour. The cache key isn't query-parametrised — there's
no user-controllable variant; the four models are fixed.

### UI structure

```
┌── Evaluation ────────────────────────────────────────────────────┐
│ Model                        Acc.  Baseline  Gain     n   Verdict │
├──────────────────────────────────────────────────────────────────┤
│ ✓ Pet-type from name         97.5%  0.0%    +97.5pp  200  pass   │  ← green row tint
│ ✓ Dietary from name + cat.   71.5%  24.5%   +47.0pp  200  pass   │
│ ✓ Segment from product       80.5%  46.5%   +34.0pp  200  pass   │
│ ✗ Return Risk                96.5%  96.5%    +0.0pp  200  FAIL   │  ← red row tint
└──────────────────────────────────────────────────────────────────┘
```

Row tints use the existing `.eval-row-pass` / `.eval-row-fail`
CSS already in `globals.css`. `.eval-mark.pass` / `.eval-mark.fail`
give the ✓ / ✗ marks. Aito panel shows the `_evaluate` body for
whichever row is currently focused (default: the failing one,
because that's the most-quoted moment).

## Acceptance criteria

- [ ] `./do dev` renders `/evaluation` with all four rows.
- [ ] Pet-type / Dietary / Segment rows show **pass** with
      visible green tint.
- [ ] Return Risk row shows **FAIL** with visible red tint and
      `accuracy_gain ≈ 0 pp`.
- [ ] Aito panel shows the live `_evaluate` body for the focused
      model.
- [ ] No regression in existing tests; the
      `test_evaluate_wraps_body_in_evaluate_key` test asserts
      the new `testSource` shape.

## Demo impact

This is demo moment #5 in `TASK.md` and the *final* of the five
moments. After this ships, **all five demo moments are live**:

| # | Moment | Where |
|---|---|---|
| 1 | Smart Search rank flip | `/smart-search` (ADR 0006) |
| 2 | For You persona switch | `/recommendations` (ADR 0007) |
| 3 | Bought Together 2.72× lift | `/bought-together` (ADR 0008) |
| 4 | Product Filling 5 fields | `/product-filling` (ADR 0009) |
| 5 | **Evaluation honest failure** | `/evaluation` (this ADR) |

The honest failure case is the most counter-intuitive part of
the demo for a sales viewer. "Look, this row's accuracy is 97 %,
so it's good, right?" — no, the gain is zero, which means
the model is doing exactly what the prior already does. The
Evaluation view's value isn't to show high numbers; it's to
show that Aito's evaluation surface tells you the truth.

## Out of scope

- **Per-case drill-down** ("which test rows did Pet-type get
  wrong"). Aito's `cases` response field carries the data but
  the UI for it is a Pattern Explorer concern.
- **Threshold customisation** in the UI. Fixed at +10 pp here.
- **Bootstrap / cross-validation across multiple test runs**.
  Aito's `_evaluate` is deterministic-ish on the same data,
  one run is enough for the demo.

## Consequences

**Good:**
- The four models cover the spread the framework doc wants:
  catalog enrichment, segment inference, cross-sell signal,
  honest failure.
- The failure case is *engineered into the data* (ADR 0002
  signal #5), so a regen with the same seed always produces
  the same honest-fail Return Risk. Reproducible.
- Parallelising the 4 calls is a small `ThreadPoolExecutor` —
  matches the Filling service's parallel `_predict` pattern.

**Bad:**
- 4 × ~10 s `_evaluate` cold cache is annoying. The 1-hour
  cache window covers the demo path; a CI gate that runs the
  full evaluation each time would need a longer budget.
- `baseAccuracy: 0.0` shows up for pet-type. Honest in panel
  copy but a reviewer who knows their stats will ask. We
  document the quirk in the ADR and accept the cost.

## Notes

- The `baseError: 1.0` / `baseAccuracy: 0.0` reading for pet-
  type from name is consistent across runs and across other
  predict targets that have very high information from the
  conditioning features. Likely Aito's "base" assumes no
  features at all and computes against the *uniform* prior
  rather than the *majority-class* prior. Doesn't affect the
  gain metric. Recorded in the cheatsheet.
