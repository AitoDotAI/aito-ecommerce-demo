# ADR 0022 — Basket rule mining (association rules as a live query)

**Status:** Proposed
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

```json
POST /api/v1/_relate
{
  "from": "order_lines",
  "where": { "product_sku.pet_type": "dog", "product_sku.category": "dry-food" },
  "relate": "order_id.line_categories",
  "limit": 12
}
```

`order_id.line_categories` reads through `order_lines.order_id →
orders.line_categories` (the denormalised `<pet>_<category>` token bag,
ADR 0008). Both `where` and `relate` are single-hop forward link
traversals — the only direction Aito allows from `order_lines` (reverse
`orders → order_lines` 400s; see the cheatsheet).

Each hit carries the rule's statistics directly:

| Field | Meaning | Rule metric |
|---|---|---|
| `related.order_id.line_categories.$has` | the consequent token (B) | rule RHS |
| `fs.fCondition` | # anchor (A) occurrences | denominator |
| `fs.fOnCondition` | # where B also present | numerator |
| `lift` | co-occurrence vs chance | rule lift |

- **Confidence** = `fOnCondition / fCondition` = P(B in the order | A on the line).
- **Lift** = the returned `lift` (> 1 positive, < 1 protective).
- **Support** ≈ `fOnCondition / total_orders` (12 215 orders). Caveat:
  the relate counts at **line** granularity, so an order with two
  dog-dry-food lines counts twice — implementation must decide
  line-vs-order support and document it.

Verified live numbers:

| Anchor | Rule | conf | lift | n (`fOnCondition`) |
|---|---|---|---|---|
| product_sku.category = dog dry-food | → dog dental-treats | 61% | 1.74 | 12 439 |
| product_sku = SKU-PT-0001 (a dog dry-food) | → dog dental-treats | 68% | 1.96 | 3 265 |
| (either) | → cat_* | — | < 0.3 | protective, dropped |

**Anchoring on a single SKU expands the condition** into that SKU's
full feature conjunction (`$and` of pet_type, category, name tokens,
tags, tax_class) — the relate treats the SKU as the set of its
features. Anchor on attribute tokens (`product_sku.category` etc.) for
clean, interpretable rule LHSs; anchor on a SKU when you want
"this exact product's basket".

## Decision

A **Basket Rules** view that mines and ranks association rules live.

1. **Anchor set** — the top-N category/attribute combinations (and,
   optionally, top SKUs by line volume) that clear a minimum support.
2. **Mine** — one link-traversal `_relate` per anchor (parallelised,
   like the Dashboard's 6-way relate fan-out).
3. **Score** — confidence = `fOnCondition/fCondition`, keep `lift`,
   support from the counts.
4. **Filter** — emit a rule only when **`lift > 1` AND `fOnCondition ≥
   50` AND confidence ≥ 0.3**. The absolute-count gate is load-bearing:
   a thin anchor (e.g. dog litter — **0 lines** in this fixture) yields
   no rule rather than a spurious 100%-confidence/n=2 artefact (the
   accounting guide's pitfall).
5. **Render** — a ranked rule table: `dog dry-food → dog dental-treats
   · conf 61% · lift 1.74 · n=12 439`, with the live `_relate` body in
   the Aito panel.

Cached 10 min (same TTL as Bought Together / Dashboard relate).

## Acceptance criteria

- [ ] A user can open `/basket-rules` and see a ranked table of
  association rules, each with antecedent, consequent, confidence,
  lift, and support count.
- [ ] Only rules passing the lift + absolute-count + confidence gate
  appear; thin/empty anchors produce no rows (no n<50 artefacts).
- [ ] Each rule's row, when selected, shows the live link-traversal
  `_relate` body that produced it in the Aito panel.
- [ ] `./do aito-check` asserts: the link-traversal relate returns
  hits for a known-good anchor, all `lift ≥ 0`, and confidence ∈ [0,1].

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
- Line-granularity counting makes support an approximation until the
  implementation pins line-vs-order semantics.
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
