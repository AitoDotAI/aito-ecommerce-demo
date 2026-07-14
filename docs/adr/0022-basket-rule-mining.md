# ADR 0022 — Basket rule mining (association rules as a live query)

**Status:** Accepted
**Date:** 2026-06-24
**Deciders:** Antti

## Context

Bought Together (ADR 0008) answers *"for this one anchor, what co-occurs?"*
— a single `_relate` over `orders.line_categories`, driven by a category
token the user picks. It's a drill-down, not a discovery tool.

The classic merchandising question is the other direction: *"mine the
whole catalogue and show me the strongest basket rules"* — association
rules `A → B` with **support, confidence, lift**. Normally that's an
Apriori/FP-growth batch job over the transaction log, recomputed on a
schedule.

`aito-accounting-demo` mines deterministic rules from a corrections
table with `_relate` *through a link* (see its
`09-relate-with-link-traversal-for-rule-mining.md`): relate the action
to the rich context reached across a link, then filter on lift +
absolute count. The same shape mines basket rules here — live, no batch
job, no precomputed rule table.

## Aito usage

**Link-traversal `_relate` from `order_lines`** — anchor on a product
(or its attributes) on the line, relate to the *order's* category bag
reached through the `order_id` link. Verified live, 2026-06-24:

**Order-level co-occurrence relate over the denormalised category-token
bag** — the Bought Together shape (ADR 0008), swept per anchor.
Verified live, 2026-06-24:

```json
POST /api/v1/_relate
{
  "from": "orders",
  "where":  { "line_categories": { "$match": "dog_dryfood" } },
  "relate": "line_categories",
  "limit":  12
}
```

Conditions on orders containing token A, relates the other tokens in
those orders. Each hit carries the rule's statistics directly:

| Field | Meaning | Rule metric |
|---|---|---|
| `related.line_categories.$has` | the consequent token (B) | rule RHS |
| `fs.fCondition` | # orders containing A | denominator |
| `fs.fOnCondition` | # of those that also contain B | numerator |
| `fs.n` | total orders (12 215) | support base |
| `lift` | co-occurrence vs chance | rule lift |

- **Confidence** = `fOnCondition / fCondition` = P(B in order | A in order).
- **Support** = `fOnCondition / fs.n` — **order-granular, always ≤ 1**.
- **Lift** = `lift` (> 1 positive, < 1 protective).

Verified live numbers (note the directional asymmetry — the point of
*rules* over symmetric co-occurrence):

| Rule | conf | lift | support |
|---|---|---|---|
| Dog dry-food → Dog dental-treats | 72% | 2.67 | 25% |
| Dog dental-treats → Dog dry-food | 94% | 2.63 | 24% |
| Cat litter → Cat wet-food | 67% | 2.17 | 2% |

### Gotcha — link traversal does NOT condition the stats per anchor

The first design tried `from order_lines where {product_sku.category:…}
relate "order_id.line_categories"`. It returns hits, but the `fs` are
**identical across different anchors** (e.g. cat-litter and cat-treats
both report `fCondition: 12886, n: 38013`) — the stats are the related
token's *global, line-granular* frequencies, not P(B | this anchor).
`n` is the order-**lines** count, which is also why support came out
> 100%. The order-bag relate above is the correct, anchor-conditioned,
order-granular shape. (Reserve the link-traversal form for the
SKU-anchored follow-up, which needs a token bag of SKUs anyway.)

## Decision

A **Basket Rules** view that mines and ranks association rules live.

1. **Anchor set** — the top-N category/attribute combinations (and,
   optionally, top SKUs by line volume) that clear a minimum support.
2. **Mine** — one order-level `_relate` per anchor (parallelised,
   like the Dashboard's 6-way relate fan-out).
3. **Score** — confidence = `fOnCondition/fCondition`, support =
   `fOnCondition/fs.n` (order-granular), keep `lift`.
4. **Filter** — emit a rule only when **`lift > 1` AND `fOnCondition ≥
   50` AND confidence ≥ 0.3**. The absolute-count gate is load-bearing:
   a thin anchor (e.g. dog litter — **0 lines** in this fixture) yields
   no rule rather than a spurious 100%-confidence/n=2 artefact (the
   accounting guide's pitfall).
5. **Render** — a ranked rule table: `dog dry-food → dog dental-treats
   · conf 72% · lift 2.67 · support 25%`, with the live `_relate` body
   in the Aito panel.

Cached 10 min (same TTL as Bought Together / Dashboard relate).

## Acceptance criteria

- [ ] A user can open `/basket-rules` and see a ranked table of
  association rules, each with antecedent, consequent, confidence,
  lift, and support count.
- [ ] Only rules passing the lift + absolute-count + confidence gate
  appear; thin/empty anchors produce no rows (no n<50 artefacts).
- [ ] Each rule's row, when selected, shows the live `_relate` body
  that produced it in the Aito panel.
- [ ] `./do aito-check` asserts: the order-level relate returns hits
  for a known-good anchor, all `lift ≥ 0`, and confidence ∈ [0,1].

## Demo impact

- New beat: **"association-rule mining as a live query"** — the rule
  table is computed on request by `_relate`, not precomputed by a batch
  Apriori run. Pairs naturally after Bought Together: BT is the
  drill-down, Basket Rules is the catalogue-wide discovery.
- `docs/demo-script.md` gains a Basket Rules beat; Bought Together
  stays as-is.

## Out of scope

- **SKU → SKU rules.** Need a denormalised `orders.line_skus` token bag
  (mirror of `line_categories`) so the relate can reach SKU tokens
  through the link. Small, additive fixture change — deferred to a
  follow-up ADR; this view ships SKU/attribute → **category** rules.
- **Multi-item antecedents** (`A ∧ B → C`). `_relate` conditions on the
  `where`; compound antecedents would need multiple conditions and
  careful support math. Not in this view.
- **Real-time Apriori / frequent-itemset enumeration.** We mine
  rules anchor-by-anchor, not the full itemset lattice.

## Consequences

**Good:**
- Market-basket analysis with no batch pipeline — the headline Aito
  story (the database *is* the rule miner), live and explainable.
- Reuses the verified `line_categories` denormalisation and the
  Dashboard's parallel-relate machinery; no new schema for the
  category-level view.

**Bad:**
- SKU→SKU (the merchandiser's real want) needs the `line_skus` fixture
  change — this view is a category-level first cut.
- Anchor-by-anchor mining isn't exhaustive itemset mining; we surface
  strong pairwise rules, not every multi-item pattern.

## Notes

- Pattern source: `aito-accounting-demo/.ai/guides/09-relate-with-link-traversal-for-rule-mining.md`.
- Builds on ADR 0008 (`line_categories` denormalisation, hyphen-stripped
  tokens) and the single-hop link-traversal limit in
  `docs/aito-cheatsheet.md`.
- New `_relate`-link-traversal pattern lands in `docs/aito-cheatsheet.md`
  with the verified body + field semantics in the implementation PR.
