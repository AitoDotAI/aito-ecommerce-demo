# Cart Completion — checkout-funnel personalisation

![Cart Completion](../../screenshots/inspect/15-cart-completion-default.png)

*Four preset checkout carts × Aito's `_relate` over
`orders.line_categories` = top add-on suggestion per scenario with
confidence + expected uplift €. Same predictive engine as Bought
Together, surfaced at the checkout funnel.*

## Overview

The question every e-commerce personalisation platform sells:
*given what's already in cart, what's the single best add to
bump basket value?* This view answers it with one Aito call per
cart — no specialised "session events" table required, just the
existing order-level co-occurrence shape.

Four preset cart scenarios cover the demo's typical buyer:

- **Dog-food starter** — premium dry-food in cart
- **Cat essentials** — wet food + litter
- **Aquarium starter** — filter pads + water conditioner
- **Dog accessory + toy** — harness + chew bone

Each scenario surfaces the cart's items + a per-scenario
"top 3 adds" panel with predicted attach confidence and the
expected € basket uplift.

## How it works

### `_relate` from orders, conditioned on cart's categories

```python
client.relate(
    table="orders",
    where={"line_categories": {"$match": "dog_dryfood"}},
    relate_field="line_categories",
    limit=10,
)
```

Same body as Bought Together. Returns the (pet, category) tokens
that co-occur most strongly with the cart's items. The service
walks the top-N related categories (excluding the cart's own) and
picks a popular product from each via a single `_search products`
call per related category.

### Why `_relate`, not `_recommend` or `_predict`

Two earlier shapes were tried and discarded:

- `_predict product_sku where {order_id.line_categories: $match}` —
  Aito's single-hop link-traversal in `where` doesn't filter the
  predict population for this query. Returns the unconditional
  product marginal across all order_lines, identical regardless
  of the cart's tokens.
- `_recommend product_sku goal {order_id.line_categories: $match}` —
  Same problem. All scenarios returned identical $p ≈ 0 hits.

`_relate` directly on `orders.line_categories` works because the
column is on the from-table (no traversal needed). The two-step
shape (categories first → products within) gives sharper results
than a one-shot product-level recommend would.

### Confidence metric

The lift from `_relate` (e.g., 1.8×) converts to a 0-1 confidence
via `lift / (lift + 1)` for display. Maps lift 2.0 → 0.67, lift
3.0 → 0.75, etc. Bounded above by 0.95 so 10× lift doesn't read
as "100 % certain". Matches the rest of the demo's $p framing.

`expected_uplift_eur = confidence × price` per suggestion — naive
on purpose. A real platform would multiply by impression × click
× conversion rate. The single multiplier is enough for the demo
to say "if this add converts, basket goes up €X".

## Key features

### 1. Cart-context-aware suggestions

Click any of the 4 scenario chips and the suggestions update.
Aquarium starter shows aquarium-adjacent products; dog-food
starter shows dental treats (the engineered dog-food → dental
lift surfaces here as well as in Bought Together).

### 2. Honest empty state

The Aquarium-starter scenario returns no suggestions when the
related-categories `_relate` produces only sub-1.15× lifts. The
view shows "No strong related categories for this cart" with an
explanation — not a broken / empty table. Pets-with-narrow-buying-
patterns deserve an honest signal.

### 3. High-ticket items lead by design

`_popular_in_category` fetches 50 candidates per related category
and sorts by `price_eur` descending. Surfaces the upsell-worthy
SKUs the merchandiser actually wants in the recommendation, not
the cheapest dental treat that happens to match.

## Data schema

No schema additions — uses `orders.line_categories` (already
denormalised for Bought Together) + `products` (price + name).

## Tradeoffs and gotchas

- **No live session state.** Each scenario is a preset cart; no
  client-side accumulation of clicks. The rep2 live-session view
  (deferred) will use the same Aito query against an event-driven
  cart.
- **No personalisation by customer profile.** The current calls
  have no `customer_segment` / `lifestyle` context. Adding them
  is a single-line `where` addition once we have a "current
  visitor" concept.
- **`_popular_in_category` sorts by price, not unit count.** Same
  popularity-proxy gotcha as Markdown.

## What this demo abstracts away

- **Real-time event ingestion** (page views, add-to-cart events,
  click streams)
- **Multi-touch attribution** for the uplift calculation
- **Promotional / coupon logic** (no "spend €X get 10 % off")
- **Free-shipping threshold upsell** ("€7 from free shipping —
  here's a €13 add-on")
- **Cart-abandonment scoring** (different question)

## Try it live

[**Open Cart Completion**](http://localhost:8500/cart-completion/).
Cold load ~6 s (4 `_relate` calls in parallel + per-suggestion
product fetches); cached for 30 minutes. Click each scenario
chip in turn — the suggestions update without a full page
reload, same way a real checkout-funnel widget would.
