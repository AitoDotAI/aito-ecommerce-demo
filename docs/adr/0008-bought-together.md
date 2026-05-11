# ADR 0008: Bought Together — order-level co-occurrence via `_relate`

**Status:** Accepted
**Date:** 2026-05-11
**Deciders:** Demo team

## Context

`TASK.md` writes Bought Together as:

> Anchor product + four cross-sell tiles with lift scores. Aito
> panel shows the `_relate` query and how lift is computed.

And in the five demo moments:

> Bought Together anchor: dry dog food → dental treats lift 3.1×;
> the panel shows the `_relate` query and the lift math.

The Dashboard ADR (0005) flagged the open question: Aito's
`_relate` over `order_lines` does **line-level** (within-row)
co-occurrence — but Bought Together needs **order-level**
co-occurrence ("given an order contains this line, what other
products appear in the same order's lines?"). Live probes for
reverse-link traversal (`order_id.<col>` back into siblings,
`$context.order_id.order_lines.…`) all returned 400.

This ADR locks the working live shape: **denormalised
`orders.line_categories` Text field + `_relate` over `orders`**.

## Aito usage

### Schema migration

```python
"orders": {
    ...
    # Space-separated `<pet_type>_<category>` tokens for every
    # line in this order. Aito tokenises Text on whitespace AND
    # hyphens, so we strip hyphens at fixture-gen time
    # (`dry-food` → `dryfood`, `dental-treats` → `dentaltreats`)
    # to keep each (pet, cat) pair as one token.
    "line_categories": {"type": "Text", "nullable": False},
}
```

### Live live query

```json
POST /api/v1/_relate
{
  "from": "orders",
  "where": { "line_categories": { "$match": "dog_dryfood" } },
  "relate": "line_categories",
  "limit": 12
}
```

Verified live (2026-05-11):

| Token (related)        | Lift  | Note |
|---|---|---|
| `dog_dryfood`          | 2.88× | self-anchor (4 149 / 4 149) |
| **`dog_dentaltreats`** | **2.72×** | **the headline demo moment** |
| `dog_wetfood`          | 1.54× | within-pet positive |
| `dog_treats`           | 1.53× | within-pet positive |
| `cat_wetfood`          | 0.27× | cross-pet anti-correlated |
| `cat_dryfood`          | 0.25× | cross-pet anti-correlated |
| `aquarium_aquarium`    | 0.03× | aquarium customers don't buy dog food |

The numbers match the local-computation reference from
`tests/test_fixtures.py` and the Dashboard's curated Python pass.
The **same lift value** now appears in three places — Dashboard
tip-box, Dashboard top-patterns bar, and Bought Together's live
panel — all driven by the same underlying signal.

### Why denormalise

The natural shape — `_relate from orders where {something
involving order_lines.product_sku} relate {something else}` —
hit 400 on every form we tried:
- `order_id.order_lines.product_sku.category` ❌ field not found
- `$context: {order_id: {order_lines: {...}}}` ❌ field not found
- `order_id.product_sku.category` ❌ field not found

Aito's `_relate` over `order_lines` does **within-row** relation
(line-level), and there's no exposed syntax for "this row's
sibling lines through the order link". The fix is the same
pattern we used for Smart Search's `customer_segment` /
`customer_pet_size`: **denormalise** the aggregate we need
directly onto the row we want to query. Cheap (one Text column,
populated at fixture-gen time), and the resulting `_relate` query
is the simplest possible shape.

## Decision

### `/api/bought-together` response shape

```ts
interface BoughtTogetherCrossSell {
  /** Group label, e.g. "Dog dental treats". Built from the
   *  (pet_type, category) the token decodes to. */
  label: string;
  /** Underlying token from the Aito response. */
  token: string;
  lift: number;
  /** `f` (overall count) and `fOnCondition` (count given the
   *  anchor is present) — surfaces "how many baskets this is
   *  computed from". Avoids quoting a sub-200 datapoint as if
   *  it were a fundamental law. */
  support: { f: number; f_on_condition: number };
  /** Top SKUs from this (pet, category) — picks the 3 most
   *  popular products in the cross-sell category so the tile has
   *  a real product to anchor on. */
  sample_skus: Array<{
    sku: string; name: string; brand: string; price_eur: number;
  }>;
}

interface BoughtTogetherResponse {
  anchor: {
    /** Synthetic anchor id like "dog__dryfood" — the (pet, cat)
     *  the user picked. */
    id: string;
    pet_type: string;
    category: string;
    display: string;        // "Dog dry-food"
    /** Sample products in the anchor (pet, cat) so the UI can show
     *  "you picked Royal Canin Dog Food 2kg" as the anchor card. */
    sample_skus: Array<{ sku: string; name: string; brand: string; price_eur: number }>;
  };
  cross_sells: BoughtTogetherCrossSell[];   // ranked by lift desc
  last_query: { endpoint: string; body: object };
  last_response_ms: number;
}
```

### Endpoint

`GET /api/bought-together?anchor=<pet>_<category>` — anchor is
the same token form the Aito query uses. Examples:
`dog_dryfood`, `cat_litter`, `aquarium_aquarium`. Default:
`dog_dryfood` (the headline moment).

Cached per anchor for 10 minutes.

### Cross-sell filtering

The raw `_relate` response includes the self-anchor (lift ≈ 3×)
and very-low-lift entries (cross-pet anti-correlated). The
service:
- Drops the self-anchor.
- Drops cross-pet anti-correlated tokens (lift < 0.5) — they're
  not "bought together", they're "bought instead of".
- Keeps the top 4 by lift.
- Resolves each token to a (pet, category) pair + a sample of 3
  real SKUs from `products` (so the tile shows a concrete
  product, not just a label).

### UI structure

```
┌── Anchor picker ───────────────────────────────────────────────┐
│  Anchor: [Dog dry-food ▾]                                       │
└────────────────────────────────────────────────────────────────┘

┌── Anchor card ───────────┐   ┌── Cross-sell tile ─────┐ ┌─ tile ─┐
│  🐕 Dog dry-food          │   │ Dog dental treats       │ │ Dog … │
│  e.g. Royal Canin Chicken │   │ e.g. Whimzees Dental    │ │       │
│  Dog Food 2kg             │   │  × 2.72  (2 954 baskets)│ │ ×1.54 │
│  €40                      │   │  €18                    │ │       │
└──────────────────────────┘   └────────────────────────┘ └───────┘
```

The anchor card uses `.rec-card` styling (compact); cross-sell
tiles use `.rec-card` + `LiftHint` for the lift chip. The Aito
panel quotes the live `_relate` body, including the `$has` /
`lift` fields read off the response.

## Acceptance criteria

- [ ] `./do dev` renders `/bought-together` with anchor =
      `dog_dryfood` and 4 cross-sell tiles. Top cross-sell is
      `dog_dentaltreats` with `LiftHint` showing `× 2.72`.
- [ ] Anchor picker shows ~6 useful anchors (dog dry-food, cat
      wet-food, cat litter, dog dental-treats, aquarium, dog
      accessories).
- [ ] Aito panel reflects the live `_relate` body with the
      anchor token in the `$match` clause.
- [ ] No regression in existing tests (20/20 still green); a
      new `tests/test_bought_together.py` adds an offline
      shape test.

## Demo impact

This is demo moment #3 in `TASK.md`. After this commit, three of
the five demo moments are live:
- #1 Smart Search (ADR 0006)
- #2 For You (ADR 0007)
- #3 Bought Together (this ADR)

The 2.72× number is now quoted live in three independent surfaces:
the Dashboard tip-box (Python-computed), the Dashboard's top-
patterns bar (Python-computed), and Bought Together (live
`_relate` against the same data). A sales conversation that
opens with the Dashboard and drills into Bought Together sees
the same number at every step — cross-page consistency without
any framework code enforcing it.

## Out of scope

- **SKU-level Bought Together** (anchor a specific product
  rather than a category pair). Possible by tokenising
  `line_skus` similarly; deferred until Pattern Explorer lands
  and we know the right ad-hoc surface for it.
- **Customer-context biasing** in the cross-sell list. The
  current shape returns universal patterns; "for cat owners,
  what's bought with dog dry-food" is a meaningful question we
  don't currently answer. Falls under Pattern Explorer (ADR
  0009).
- **Live dashboard rewrite**. The Dashboard's top-patterns
  block still uses the Python pass; converting it to live
  `_relate` calls is a one-PR follow-up after this ADR ships.

## Consequences

**Good:**
- The headline live `_relate` query is now in the cheatsheet.
  Pattern Explorer can lift this shape directly.
- The Dashboard's Python pass becomes a strict reference
  computation; the *live* numbers are now also accessible and
  match.
- Schema migration is small (one Text column on `orders`); the
  generator already iterates lines per order so populating
  `line_categories` costs nothing.

**Bad:**
- Two denormalised columns now — `order_lines.customer_segment`
  / `customer_pet_size` (ADR 0006) and `orders.line_categories`
  (this ADR). Both fall out of date if their source tables
  change; we treat them as one-shot at fixture-gen time. A
  real-world version would maintain them via change-data-
  capture; the demo doesn't need that complexity.
- Aito tokenising Text on hyphens forced the
  `dry-food` → `dryfood` rewrite. The token form is now
  schema-internal; the UI maps tokens back to "Dog dry-food"
  for display. Not visible to a panel reader but worth knowing
  if you ever look at `orders.line_categories` raw.

## Notes

- The same Text-tokenisation trick generalises: any
  cross-table "set" feature can ride on a single denormalised
  Text column. If Pattern Explorer needs e.g.
  `customers.purchased_brands`, the same recipe applies.
- The lift threshold for keeping a cross-sell tile (`> 0.5`) is
  a design choice. Below that, the pattern reads as "people who
  bought X did NOT buy Y" — useful for Pattern Explorer's
  protective-pattern story, not for Bought Together's
  cross-sell narrative.
