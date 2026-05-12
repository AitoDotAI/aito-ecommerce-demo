# Feedback — review triage via multi-field `_predict`

![Feedback](../../screenshots/09-feedback.png)

*Free-text review in, four structured fields out. Aito predicts
category, sentiment, the suggested support-team assignee, AND a
forward-looking 90-day churn risk — all from the review's text
alone, in one round-trip via four parallel `_predict` calls.*

## Overview

Customer support teams triage reviews manually: read the text,
decide what the issue is (shipping problem? quality complaint?
sizing question? praise?), tag the sentiment, route it to the
right team member. The work doesn't scale linearly with volume
and most of it is pattern-matching the team has done a thousand
times before.

Feedback runs the classifier. Aito's `_predict` over the review's
`text` Text column returns the three fields in parallel — the
agent opens the queue, the predictions are already there with
confidence chips and the option to override.

## How it works

### Four parallel `_predict` calls

```python
# src/feedback_service.py — get_feedback()
where = {"text": review["text"]}

with ThreadPoolExecutor(max_workers=4) as pool:
    futures = [
        pool.submit(_predict_field, client, where, predict_field, label)
        for predict_field, label in [
            ("category",         "Issue category"),
            ("sentiment",        "Sentiment"),
            ("assigned_to",      "Suggested assignee"),
            ("churn_within_90d", "Churn risk (90 d)"),
        ]
    ]
    fields = [f.result() for f in futures]
```

Each call shape is identical apart from `predict`:

```json
{
  "from": "reviews",
  "where": { "text": "Package arrived late. The seal was broken." },
  "predict": "category",
  "select": ["$p", "feature", {"$why": {}}],
  "limit": 5
}
```

Wall-clock = the slowest of three — typically ~280 ms warm,
~1 s cold.

### Why the Text-column conditioning works

`reviews.text` is declared with `analyzer: "whitespace"`. At
index time Aito tokenises each review's body and indexes the
tokens as features.

At query time, `where: {text: "Package arrived late ..."}`
matches rows in the training data whose `text` contains the same
tokens, and the `_predict` returns the most probable value of the
target field given that token overlap.

Aito learns, for example, that reviews containing "arrived" +
"late" + "package" cluster in `category=shipping` and route to
`assigned_to=Anna`. The model is implicit; the training set is
the existing reviews table.

### Ground-truth comparison

Reviews ship with their labels (`category`, `sentiment`,
`assigned_to`) in the fixture. The frontend renders a "✓ matches
stored" / "≠ expected" pill next to each prediction so a reviewer
can spot-check accuracy on the page.

```python
@dataclass(frozen=True)
class ReviewSummary:
    # ...
    actual_category: str
    actual_sentiment: str
    actual_assigned_to: str
```

This is per CLAUDE.md prime directive #2 — show the honest
comparison. Aito gets `category` right ~88% of the time on the
fixture data; `assigned_to` is ~95% because it's deterministically
mapped from category in the training data.

## Key features

### 1. Same shape as Product Filling

The fanout pattern is identical: N parallel `_predict` calls with
shared `where`, different `predict` per call, render each result
in its own field card. Two worked examples of "multi-field
predict for catalog enrichment" applied to two very different
domains.

### 2. Confidence-aware rendering

Each prediction's confidence (Aito's `$p`) drives the chip color:
green ≥ 0.85, yellow 0.5-0.85, red < 0.5. A 92% prediction reads
visually different from a 53% one; the agent's eye goes to
the low-confidence cases first.

### 3. `$why` factors per field

Clicking the question mark next to any predicted field opens the
WhyTooltip with the top contributing tokens — e.g. for
`category=shipping`, the factors might be:
"text token 'late': lift 4.2×",
"text token 'arrived': lift 2.8×".
Auditable predictions, not a black box.

### 4. Churn risk from text alone

The 4th predict `churn_within_90d` is the demo's connection from
feedback to retention. Given just the review's text, Aito returns
P(this reviewer churns within 90 days). High-risk reviews
(complaints about shipping, repeated quality issues) light up red
at 60-80%; positive reviews stay green near 8-15%.

The label is set per review at fixture-gen time:
`churn_within_90d` = True iff the reviewer has no orders in
the 3 months after the review's `created_at`. Reviews written
near a churning customer's last order have True labels; reviews
written during active periods have False. Aito learns "these
text patterns predict the reviewer is on their way out" without
ever seeing the customer's order history.

## Data schema

```json
{
  "reviews": {
    "type": "table",
    "columns": {
      "review_id":       { "type": "String" },
      "customer_id":     { "type": "String", "link": "customers.customer_id" },
      "product_sku":     { "type": "String", "link": "products.sku" },
      "rating":          { "type": "Int" },
      "text":            { "type": "Text", "analyzer": "whitespace" },
      "category":        { "type": "String" },
      "sentiment":       { "type": "String" },
      "assigned_to":     { "type": "String" },
      "created_at":      { "type": "String" },
      "churn_within_90d": { "type": "Boolean" }
    }
  }
}
```

Two link columns (`customer_id`, `product_sku`) anchor reviews
to real customers and real products — the UI surfaces the
linked product name + customer label from the review card.

## Tradeoffs and gotchas

- **Template-generated text limits the demo's depth**. The
  reviews are fixture-generated from per-category templates
  (~6 templates × 5 categories). Aito learns the templates
  rather than the underlying concepts. On real customer data
  with varied phrasing, accuracy would drop and the value of
  `$why` would rise.
- **`assigned_to` is deterministically mapped from `category`**
  in the training data. This makes Aito's `assigned_to`
  prediction trivial (95%+ accuracy) — it learns the mapping in
  one shot. A real support team has imperfect routing; the demo
  could model that with a noisy mapping.
- **No multi-language support**. The fixture is English-only.
  Aito tokenises whitespace; a Finnish review with hyphens or
  compound words would tokenise differently.
- **Per-review caching**. Cache key is `feedback:{review_id}`.
  Same review id always returns the cached prediction; flipping
  reviews triggers a fresh fan-out.

## What this demo abstracts away

- **Reply drafting**. Predicting the category + sentiment +
  assignee is half the support workflow; the other half is
  drafting the reply. A follow-up view could use `_recommend`
  over resolved tickets ("of similar past tickets, which
  resolution worked?").
- **Per-review escalation**. The view shows the prediction but
  doesn't let the user accept / override / escalate. Production
  wires those actions to a tickets table.
- **Sentiment drift**. The view is per-review. Cohort-level
  sentiment over time belongs in Pattern Explorer or a new
  trend surface.
- **Image attachments**. Reviews are text-only.

## Try it live

[**Open Feedback**](http://localhost:8500/feedback/) and pick a
review from the dropdown. The three predicted fields render in
under 300 ms warm; the Aito panel shows the live query body.

```bash
./do dev
# → http://localhost:8500/feedback/
```
