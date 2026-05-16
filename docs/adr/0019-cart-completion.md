# ADR 0019 — Cart-completion view

**Status:** Accepted

## Context

The e-commerce expert critique flagged "no conversion-funnel
moment" as the biggest gap between this demo and what
personalization-platform buyers expect. Cart-abandonment vs upsell-
at-checkout is the question they walk in with. Bought Together
shows category co-occurrence but stops at "treats follow dog
dry-food"; the checkout funnel needs specific products.

Cart Completion fills that gap with a static-cart simulator: four
preset cart shapes (dog-food starter / cat essentials / aquarium
starter / dog accessory + toy), each runs one Aito call and
surfaces 3 add-on products with predicted attach confidence and
expected basket-uplift €.

The view is a stepping stone toward the rep2-only live-session
view (where clicks drive the recommendation live). Same underlying
Aito query shape; just preset scenarios instead of an event stream.

## Decision

### Aito query shape

For each preset cart, one call:

```json
POST /api/v1/_relate
{
  "from":   "orders",
  "where":  { "line_categories": { "$match": "dog_dryfood" } },
  "relate": "line_categories",
  "limit":  10
}
```

Same shape as Bought Together. Returns the categories that
co-occur most strongly with the cart's tokens. We then walk the
top-N related categories (excluding cart's own), pick a popular
product from each via a small `_search products` call, and surface
the top 3 products as suggestions.

### Why `_relate`, not `_recommend` or `_predict`

Two earlier shapes were tried and rejected:

- `_predict product_sku where {order_id.line_categories: $match}` —
  Aito's single-hop link-traversal in `where` doesn't filter the
  predict's training population. Returns the unconditional product
  marginal across all order_lines, identical regardless of the
  cart's tokens.
- `_recommend product_sku goal {order_id.line_categories: $match}` —
  Same problem, the goal-side traversal doesn't bite. All
  scenarios returned identical $p≈0 hits.

`_relate` directly on `orders.line_categories` works because the
column is on the from-table (no traversal needed). The two-step
shape (categories first, then products within them) gives sharper
results than a one-shot product-level recommend would.

### Confidence metric

The lift from `_relate` (e.g., 1.8×) is converted to a 0-1
confidence via `lift / (lift + 1)` for display. Maps lift 2.0 →
0.67, lift 3.0 → 0.75, etc. Bounded above by 0.95 so 10× lift
doesn't read as "100 % certain". Same readout convention as the
rest of the demo's $p-like numbers.

`expected_uplift_eur = confidence × price` per suggestion. Naive
on purpose — a real platform would multiply by impression rate ×
click rate × conversion. The single confidence × price multiplier
is enough for the demo to say "if this add converts, basket goes
up €X".

### Popularity within category

`_popular_in_category` runs a small `_search` on `products` with
`(pet_type, category)` equality. Sort order is whatever Aito
returns — production code would join `monthly_sales` for a real
popularity ranking. The demo's purpose is showing a specific SKU
per related category, not winning the popularity-algorithm war.

## Acceptance criteria

- A user can pick any of the 4 preset carts and see its 2 items +
  Aito's top 3 add-on suggestions.
- Each suggestion shows name, brand, category, price, confidence,
  expected uplift €.
- Aquarium-only cart (which the dataset's narrow co-occurrence
  signal can't recommend for) shows an empty state with an honest
  "no strong related categories" message — not a broken table.

## Demo impact

- Closes the "where's the checkout-funnel moment?" gap.
- Reuses the predictive engine the Bought Together view already
  showcases — different surface, same Aito mechanism.
- Sets up the rep2 live-session view: when reps2 lands hot-warm
  cache, the same Aito call can run on click-by-click cart state.

## Out of scope

- **Real-time session state.** Each call here uses a preset cart;
  no client-side accumulation of clicks. Live session needs rep2
  background-refresh writes (see TODO note in scaling.md).
- **Personalization by customer profile.** The current calls have
  no `customer_segment` / `customer_lifestyle` context. Adding
  them would be a single-line where addition once we have a
  "current visitor" concept (which the rep2 view will introduce).
- **Cart-abandonment scoring.** Different question (P(complete) vs
  "what to add"); different model.

## References

- Bought Together's `_relate` shape — ADR 0008.
- `line_categories` denormalisation rationale — ADR 0002.
- Pretty pictures and demo critique that motivated this view —
  conversation log §"E-com expert hat".
