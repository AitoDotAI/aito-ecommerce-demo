# ADR 0007: For You — personalised tile grid + persona switcher

**Status:** Accepted
**Date:** 2026-05-11
**Deciders:** Demo team

## Context

`TASK.md` writes For You as:

> Personalised tile grid for a selected customer, with a
> customer-switcher pill bar to flip context live (Maija / Olli /
> Saara). Aito panel shows `_recommend` with `goal` (probability
> of purchase) and `where` (customer profile). … switching from
> Maija (cat owner) to Olli (multi-pet, small dog) flips the
> entire recommendation grid in <300 ms.

Smart Search (ADR 0006) already proved the
`_recommend goal: {customer_segment, customer_pet_size}` shape
produces a clean per-persona flip. For You reuses the same
pattern, drops the `name $match` filter, and shows results as a
tile grid rather than a side-by-side table.

The probe surfaced one trade-off that this ADR locks in.

## Aito usage

### Query shape — same as Smart Search, name filter dropped

```json
POST /api/v1/_recommend
{
  "from": "order_lines",
  "where": {},
  "recommend": "product_sku",
  "goal": {
    "customer_segment": "cat_owner"
  },
  "limit": 12
}
```

Ranks every product by **P(this segment | line contains this
product)**. With the name filter dropped, we see the segment's
*whole* shopping preference, not just the food slice.

### Persona-goal table (live, 2026-05-11)

| Persona pill              | `customer_segment` | `customer_pet_size` | Top-3 categories | Note |
|---|---|---|---|---|
| Maija — cat owner         | `cat_owner`        | `null`     | cat × litter, cat × dry-food, cat × dry-food | strongly cat |
| Olli — multi-pet (small dog) | **`dog_owner`** | `small`    | dog × dry-food, dog × accessories, dog × treats | see "Olli divergence" below |
| Saara — large breed dog   | `dog_owner`       | `large`    | dog × grooming, dog × dry-food, dog × accessories | large-breed kibble dominates |

### Olli divergence — why goal differs from his customer record

Olli's `customers.segment` is `multi_pet` per ADR 0002 (the multi-
pet persona). But Aito's segment-level conditioning treats
`multi_pet` as the **whole multi-pet population** (50 % dog, 45 %
cat per `SEGMENT_PET_TYPE_WEIGHTS`). His hand-curated personal
history is 85 % dog (`pet_type_weights` override in the persona
table) — but the segment-level query doesn't see his individual
rows, it sees the segment's average.

That makes Maija → Olli look like a near-noop in the segment
view (both lean cat in aggregate), which breaks the TASK.md
"flips the entire grid" moment.

**The fix**: For You's `_recommend` *goal* uses `dog_owner +
small` for Olli — the segment that *his actual purchase pattern
fits*. The UI keeps the "multi-pet, small dog" label (so the
TASK.md persona description holds), and the Aito panel honestly
shows the goal body that ran.

This is *not* personalisation by customer_id (which we've already
shown under-fits on the 3 000-customer dataset). It is **persona
labelling** — the three demo personas have hand-picked goal
contexts that produce the cleanest flips. The session log records
this and the cheatsheet calls it out as a "demo-time goal
override" pattern.

### What For You does *not* do

- **Per-customer (`order_id.customer_id`) goal.** Too thin for
  the dataset; results don't differentiate the personas
  (confirmed in the Smart Search probe, step 6).
- **Hide products the customer has already bought.** Filtering
  out historical purchases would require an extra round-trip and
  costs the visible 300 ms target. Not worth it for the demo —
  the tile grid showing "products you've bought before"
  alongside new picks is realistic anyway.

## Decision

### `/api/for-you` response

```ts
interface ForYouTile {
  sku: string;
  name: string;
  brand: string;
  pet_type: string;
  category: string;
  price_eur: number;
  rank: number;
  /** P(segment | product) from Aito. Surfaced as a per-tile
   *  "× 0.91" chip so the visitor sees the ranking signal. */
  score: number;
}

interface ForYouResponse {
  persona: {
    id: string;            // "maija" | "olli" | "saara"
    label: string;         // "Maija — cat owner"
    segment: string;       // the goal's segment (may differ from customer record — see ADR)
    pet_size: string | null;
    customer_id: string;   // the underlying CUST-NNNNN
  };
  tiles: ForYouTile[];
  last_query: { endpoint: string; body: object };
  last_response_ms: number;
}
```

### Endpoint

`GET /api/for-you?customer=<persona_id>` — same persona ids as
Smart Search (`maija`, `olli`, `saara`).

Cached per persona for 5 minutes. Flips within the cache window
hit memory directly — well under the 300 ms target.

### UI structure

```
┌── Persona pill bar ────────────────────────────────────────────┐
│  ◉ Maija (cat owner)   ○ Olli (multi-pet)   ○ Saara (large dog) │
└────────────────────────────────────────────────────────────────┘

For Maija — cat owner    · 12 picks    · last query 38 ms

┌────────┬────────┬────────┬────────┐
│ 🛒    │ 🛒    │ 🛒    │ 🛒    │   ← rec-card grid from globals.css
│ name  │ name  │ name  │ name  │      (rec-grid · 4 cols ≥ 1280px,
│ brand │ brand │ brand │ brand │       3 cols 900-1279, 2 cols <900)
│ €X.XX │ €X.XX │ €X.XX │ €X.XX │
│ p=.91 │ p=.91 │ p=.91 │ p=.89 │
└────────┴────────┴────────┴────────┘
…
```

Each tile uses the existing `.rec-card` / `.rec-card-body` /
`.rec-card-name` / `.rec-card-brand` / `.rec-card-price` /
`.rec-card-score` classes already in `globals.css`. Pill row and
search-style pill states reuse the `.customer-chip` classes.

Aito panel: `_recommend` endpoint badge active; the panel's
`query` block updates with the actual goal body on every flip.

## Acceptance criteria

- [ ] `./do dev` renders `/recommendations` with the persona pill
      bar defaulting to Maija and a 12-tile grid of cat-leaning
      products in her column.
- [ ] **Maija → Saara flip**: ≥ 10 of the 12 tiles change SKU;
      visually the grid swaps cat → dog products.
- [ ] **Maija → Olli flip**: ≥ 8 of the 12 tiles change SKU;
      visually the grid swaps cat → dog products (Olli's goal
      override).
- [ ] Persona flip end-to-end **under 300 ms** when the cache
      is warm (the cold path is ~150 ms for the live
      `_recommend` call).
- [ ] Aito panel `query` block reflects the live goal body
      including `customer_pet_size` when set.
- [ ] No new test regressions (offline test for the persona
      mapping; live test for the rank-flip is a smoke check).

## Demo impact

For You is demo moment #2 in `TASK.md`. The combination of
Smart Search (moment #1) + For You (moment #2) makes the
"predictive application" narrative concrete: same dataset, three
predictive surfaces, two different `_recommend` query shapes
(name-filtered + unfiltered), and the same `goal` differentiator
on both.

## Out of scope

- **Per-line `$why` decomposition.** Tiles are compact; the
  `WhyTooltip` per tile would over-crowd the grid. We carry the
  per-tile probability as a single chip and leave detailed `$why`
  for views where it belongs (Pattern Explorer, Product Filling).
- **Filtering by category / price.** Tile grid is a flat top-N;
  filters are a Purchase Analytics concern.

## Consequences

**Good:**
- Reuses Smart Search's locked query shape — no new Aito work.
- Persona pill bar UX is consistent with Smart Search; visitors
  who use Smart Search first recognise the pattern.
- 5-min cache + ~150 ms cold call means the flip target lands
  with margin.

**Bad:**
- Persona-goal override on Olli is a small honesty trade-off.
  We surface it in the panel via the verbatim `goal` body, and
  in the demo-script via the "Olli's shopping pattern fits
  dog_owner_small even though his household has a cat too" line.
  The alternative — relabelling the customer record itself —
  would break the multi-pet persona that other views (Bought
  Together, the dashboard segment cards) reference.

## Notes

- The 300 ms target is browser-side end-to-end (click → tiles
  rendered). The Aito call's wall time is ~150 ms cold and
  ~12 ms cached. `LatencyBadge` on the topbar makes the
  user-visible latency observable during the demo.
