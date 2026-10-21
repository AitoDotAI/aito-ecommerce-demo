# For You — personalised tile grid with live persona switching

![For You](../../screenshots/03-for-you.png)

*Personalised product grid for the active persona. Click any pill
in the persona bar above (Maija / Olli / Saara) and the 12-tile grid
re-ranks: same query body, a different customer id in `where`.*

## Overview

For You is the "what should this customer see on the home page"
view. It reuses Smart Search's conversion-KPI shape (ADR 0021): the
same `impressions` table and `goal: {purchased: true}`, without a
search query, so the result spans every category the customer buys.

After Smart Search shows the rank flip for a query, For You shows the
same effect across the whole catalogue for Maija (cat owner), Saara
(large-breed dog owner) and Olli (a small dog and a cat, mostly dog).

## How it works

### The query

```python
# src/recommend_service.py — get_for_you()
where = {"context.customer": persona.customer_id}
goal = {"purchased": True}

client.recommend(
    table="impressions",
    where=where,
    recommend_field="product_sku",
    goal=goal,
    limit=limit,     # 12
)
```

The body the Aito panel shows for Maija:

```json
{ "from": "impressions",
  "where": { "context.customer": "CUST-00001" },
  "recommend": "product_sku",
  "goal": { "purchased": true },
  "limit": 12 }
```

`context.customer` is two links from `impressions`: each impression
links to its `context` (the visit), which links to the `customer`.
Aito learns the persona from their own rows; no segment, pet size or
trait is handed to it (ADR 0033). That also retires ADR 0007's "Olli
divergence", where Olli's goal had to be overridden to a dog segment:
his mostly-dog history speaks for itself.

The frontend issues one call per persona switch, cached for 5 minutes.

### Score on each tile

Each tile renders Aito's `$p`: the probability that this customer buys
the product when it is shown, P(purchased | this customer).

## Key features

### 1. Same table and goal as Smart Search

For You is Smart Search's purchase model without the text. Sharing the
shape keeps the Aito panel, the cache and the "what's a recommendation"
mental model the same across the two views.

### 2. The grid flips between personas

Each persona's grid follows what that customer has bought: Maija's
leans to cat products, Saara's to dog products. That's the customer's
own history driving the catalogue's presentation. `./do aito-check`
checks the flip live.

## Data schema

```json
{
  "impressions": { "columns": {
    "context":     { "type": "String", "link": "contexts.context_id" },
    "product_sku": { "type": "String", "link": "products.sku" },
    "purchased":   { "type": "Boolean" } } },
  "contexts": { "columns": {
    "context_id": { "type": "String" },
    "customer":   { "type": "String", "link": "customers.customer_id" } } }
}
```

Only the columns For You uses are shown; `src/schema.py` has the rest.

## Tradeoffs and gotchas

- **The grid doesn't update on add-to-cart.** The Shop view does that:
  the cart goes into its `where` as context.
- **The first tile row dominates the visual diff.** The row that most
  cleanly shows the persona effect is the top row; Pattern Explorer is
  the right surface for the long tail.

## What this demo abstracts away

- **A real recommendation engine** would blend several signals
  (collaborative, content, recency, diversity) and learn from
  click-throughs. For You is one `_recommend`.
- **Cold start.** A customer with no impressions has nothing for Aito
  to learn from; a real product would fall back to all impressions or
  to what the customer declared (the Shop's "Picked for you" uses the
  declared pets).
- **Catalogue freshness.** Out-of-stock and price-tier filters would be
  layered on top of the `_recommend` result.

## Try it live

[**Open For You**](http://localhost:8500/recommendations/) and
click the persona pills above the grid. The entire grid re-renders
in <300 ms — watch the Aito panel on the right show the live
`_recommend` body that ran for the active persona.

```bash
./do dev
# → http://localhost:8500/recommendations/
```
