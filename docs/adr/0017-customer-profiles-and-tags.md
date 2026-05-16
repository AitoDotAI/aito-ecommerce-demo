# ADR 0017 — Customer-profile traits, product tags, real names

**Status:** Accepted

## Context

The PetNord fixture's customers were segment-driven and otherwise
uniform: within `segment = dog_owner`, every customer bought roughly
the same brand mix, dietary mix, and category mix. That made Aito's
prior-feature inference (`_recommend basedOn`) informationally
redundant — the segment goal already determined the answer for any
customer with more than a few orders. It also flattened the Pattern
Explorer / Bought Together / Purchase Analytics views: most
within-segment patterns washed out into segment-level base rates.

We wanted four things from the data:

1. Make `_recommend basedOn: ["tags", "brand", "dietary", ...]`
   carry real signal even on thin-history customers — so the demo
   shows "after 3-4 purchases, Aito identifies the cat person" as
   a visible moment.
2. Inject within-segment patterns that Pattern Explorer / Bought
   Together / Purchase Analytics can surface as compelling
   archetype-specific behaviour.
3. Give Aito a denser product-side feature column (`tags`) that
   adds lifestyle and use-case dimensions orthogonal to existing
   categorical columns.
4. Make the UI feel like a real Finnish pet shop — customers as
   Aino Korhonen / Mikko Mäkelä, not CUST-00042.

## Decision

Add three things to the fixture, layered on the existing engineered
signals (large-breed cat share, dog-food → dental lift, persona
top-5 overlaps) without perturbing them:

### 1. Four latent customer-profile traits on `customers`

| Column | Values | Distribution | Drives |
|---|---|---|---|
| `lifestyle` | premium / mid / budget | 25/50/25 with per-segment bias | Brand-tier choice; basket value; return rate |
| `health_focus` | high / medium / low | 25/50/25 | Wellness-dietary share (grain-free / sensitive / senior / weight-control) |
| `treat_affinity` | high / medium / low | 25/50/25 | Treats + dental-treats share |
| `brand_loyalty` | loyal / flexible | 30/70 | Top-2 brand concentration |

Sampled at customer creation, stable across the customer's entire
purchase history. Personas (Maija / Olli / Saara) get hand-curated
values matching their narrative.

Loyal customers also get a `favorite_brands` tuple (1-2 brands,
constrained to segment + lifestyle compatibility). In-memory only —
not in the JSON output, because it's a derived view of
`brand_loyalty`. The order-generation loop uses it to concentrate
loyal customers' purchases on 1-2 brands (median top-2 share: 73 %
loyal vs 55 % flexible — measured on customers with ≥5 orders).

### 2. `tags` text column on `products`

Space-separated lifestyle markers synthesised from existing
attributes:

- Brand-tier: `"premium"` (Royal Canin / Hill's / Acana / Orijen)
  or `"mass"` (PetNord / Eukanuba / Whiskas / Kong / Trixie /
  JBL / Tetra / Beaphar). Tier-neutral brands contribute neither.
- Dietary translated to consumer wording: `grain-free → "natural"`,
  `senior → "senior-care"`, `puppy → "puppy-stage"`, etc.
- Category lifestyle markers: dry-food → `"complete kibble"`,
  dental-treats → `"dental training preventive"`, toys →
  `"interactive chew"`, etc.
- Price ≥ €30 → `"value-bundle"` (bulk-size marker).

5-8 tags per product. Stored as `Text` (whitespace-analyzed) so
both `_search { tags: $match }` and `_recommend basedOn: ["tags"]`
work without extra schema.

### 3. Customer display names

Finnish first + last names, deterministic per `customer_id`, unique
across the dataset. Pre-shuffled deck of 76 first × 50 last = 3 800
combinations against 2 997 generic customers ⇒ no collisions,
unaffected by retry gymnastics. Personas keep their hand-curated
narratives:

- `CUST-00001` Maija Lehtonen (cat owner)
- `CUST-00002` Olli Mäkelä (multi-pet, small dog)
- `CUST-00003` Saara Virtanen (large-breed dog owner)

Denormalised onto `customer_months.customer_name` so the Churn
at-risk list renders real names without an extra Aito hop. UI:
`recommendations` + `smart-search` persona pills show the full
name; `churn` at-risk list pulls from `customer_months` directly.

### Engineered cross-trait correlations

The four traits drive each line's product pick via
`_customer_preference_substitute` (replaces the prior
`_apply_segment_affinity`):

| Trait | Multiplier | Effect on chosen product |
|---|---|---|
| `lifestyle = premium` | ×2.6 for premium brands; ×0.55 for mass | Premium customers buy 53 % premium brands vs budget 32 % (within dog) |
| `lifestyle = budget` | ×2.2 for mass brands; ×0.50 for premium | |
| `health_focus = high` | ×2.4 for wellness dietary; ×0.65 for lifestage | High-health 81 % wellness-dietary share vs low 58 % |
| `health_focus = low` | ×0.55 wellness; ×1.3 lifestage | |
| `treat_affinity = high` | category-bias ×2.7 on treats + dental-treats | High-treat customers 31 % treats+dental share vs low 13 % |
| `treat_affinity = low` | category-bias ×0.40 on treats + dental-treats | |
| `brand_loyalty = loyal` | 85 % snap to favorite-in-slice | Median top-2 brand share 73 % loyal vs 55 % flexible |

Plus integration with the existing churn signal:

- `lifestyle = budget` → +8 pp churn propensity
- `lifestyle = premium` → −4 pp
- `brand_loyalty = flexible` → +4 pp
- `brand_loyalty = loyal` → −4 pp

Churn rate by (lifestyle, loyalty):

```
(budget, flexible)   41 %
(budget, loyal)      41 %
(mid, flexible)      38 %
(mid, loyal)         29 %
(premium, flexible)  33 %
(premium, loyal)     36 %
```

And lifestyle-modulated returned share (`returned` column on
`order_lines`):
- premium: 1.8 %
- mid: 3.0 %
- budget: 4.2 %

Overall returned share stays in the 2.5-3.5 % band that signal-
test #5 asserts.

## Why this shape works for `basedOn`

Per ADR 0017 §"When do priors actually move the ranking?" in the
cheatsheet (and discussed at length with the core team), `basedOn`
priors contribute when the direct candidate-identity signal is
sparse — cold candidates or thin context slices. The pre-engineering
fixture made *every* persona thick (segment + pet_size already
saturated the goal), so priors had nothing to add.

The latent traits engineer per-customer signal that's:

- **Stable across the customer's purchase history** — so 3-4
  observations of "premium brand + grain-free dietary" let Aito
  infer the customer's pattern, then the same pattern propagates
  to recommend-time scoring of unseen products.
- **Orthogonal to segment + pet_size** — the where + goal in
  smart-search already encode segment; the latent traits add
  within-segment signal that priors can pull.
- **Surfaced at the product feature level** (brand, dietary, tags),
  so `basedOn: ["tags", "brand", "dietary"]` reaches them.

## Aito usage

- `customers` schema gains `name, lifestyle, health_focus,
  treat_affinity, brand_loyalty` columns.
- `products` gains `tags` (Text, whitespace-analyzed).
- `order_lines` gains denormalised
  `customer_lifestyle, customer_health_focus,
  customer_treat_affinity, customer_brand_loyalty` (single-hop
  traversal limit).
- `customer_months` gains the same four denormalised traits plus
  `customer_name` for the Churn at-risk UI.

## Acceptance criteria

- A user can see real Finnish names in the Churn at-risk list,
  smart-search persona pills, and For-You persona pills.
- Pattern Explorer's `_relate` over `customer_lifestyle ↔ brand` /
  `customer_health_focus ↔ dietary` surfaces meaningful
  within-segment lifts.
- `_recommend basedOn: ["tags", "brand", "dietary"]` rankings on
  thin-history customers (orders ≤ 3) reflect the customer's
  lifestyle / health-focus pattern.
- All existing signal tests pass (no regression on persona
  overlaps, dog-food → dental lift, large-breed cat share, returned
  share band).

## Demo impact

- **Smart-search**: priors now have signal even for cold customer
  contexts — "this is what a dog-person buys" is visibly inferable.
- **Churn**: the at-risk list reads like a real customer list ("Aino
  Korhonen", not "CUST-00042"), and the engineered churn-by-profile
  rate gap (budget+flexible 41 % vs mid+loyal 29 %) gives
  `_relate churned=true` more drivers to surface.
- **Pattern Explorer**: 5 new categorical columns to relate on
  (`lifestyle`, `health_focus`, `treat_affinity`, `brand_loyalty`,
  `tags` via `_match`).
- **For-You**: persona pills feel like a real shop's customer
  switcher.

## Out of scope

- **Day-of-week / seasonal preferences.** The grocery generator
  has these via `ShoppingDayPreference`; we deferred — current PR
  is already large.
- **Per-product idiosyncratic preference** (the grocery
  `SpecificProductPreference`). Orthogonal to the trait-driven
  signal; doable as a follow-up if useful.
- **Visit / impression model.** Grocery generates explicit
  `Impression` rows for non-purchase recommendations; we don't
  surface them in any view today.

## References

- GroceryData.scala in aito-core — the source pattern for
  composable user-preference layers.
- Aito core team's note on `basedOn` and slice density —
  `docs/notes/aito-perf-findings.md` §5.
