# Evaluation accuracies under grouped hold-outs

Measured 2026-09-30, read-only, on the shared instance (v2) with
`scripts/evaluation_holdouts.py`. The script reads the rows from Aito, so it
measures exactly what the page is scored on.

## Why

The Evaluation page's `_evaluate` holds out random **rows**. That leaks when
rows come in groups sharing the answer:
- a product's size variants share its pet type and diet (452 of 658 products
  share their name, minus the size, with another);
- a customer's order lines share their segment.

Each model is re-scored with `_predict` over a nested `from` that removes the
test item's whole group. The same items are also scored with only the row
held out (the page's method), and pooled.

## Design (pre-registered before the runs)

- **Sample:** 150 product families (pet type, dietary) or 200 customers
  (segment), `random.Random(0)`, one item per group.
- **Arms,** all through a nested `from`:
  - pooled: excludes nothing;
  - row held out: excludes the item;
  - group held out: excludes the family (`$not` name `$match` family) or
    the customer (`$not` `order_id.customer_id`).
- **Control:** pooled against a plain `from`.
- **Decision rule, fixed in advance:** the group-held-out accuracy must clear
  the majority baseline by ≥ 10 points (the page's pass threshold). The page
  then shows the group-held-out number.

The pet-type pre-registration had two arms (pooled and family held out). The
row-held-out arm and the control were added in the traced run, after the
pre-registration.

## Results

| model | pooled | row held out | **group held out** | group − row (95 % CI) | baseline | verdict |
|:--|--:|--:|--:|:--|--:|:--|
| pet type from name | 0.953 | 0.920 | **0.867** (family) | **−0.053 [−0.100, −0.013]** | 0.422 | pass |
| dietary from attributes | 0.820 | 0.773 | **0.773** (family) | +0.000 [−0.033, +0.033] | 0.267 | pass |
| segment from product | 0.840 | 0.840 | **0.830** (customer) | −0.010 [−0.025, +0.000] | 0.458 | pass |

**Pet type:** the row hold-out the page uses **is inflated** by the
size-variant leak, by about 5 points on this sample (the interval excludes
0). The model still passes by a wide margin. The page should show the
family-held-out number.

**Dietary:** no leak beyond holding the row out. The page's own 0.65 is lower
because its `_evaluate` also scores products with no dietary tag, which this
sample excludes. That's a different population, not inflation.

**Segment:** a negligible customer-level leak (the interval reaches 0), as expected: the evidence is product-level only (pet type and category), so one customer's other lines barely move the estimate. The page's 0.82 matches.

## Controls

- **Pooled nested `from` vs plain `from`:** identical top-1 predictions on
  every item, for every model.
- **`$p`:** for the same evidence, an exclude-nothing nested `from` returns
  **byte-identical** probabilities to a plain `from` (checked on dog /
  dry-food → segment: 0.777321 / 0.175879 / 0.023769). So the mechanism
  doesn't shift results; differences between arms are the removed rows.
- **Per-row sensitivity:** removing one row moved P(dog_owner) by 0.005,
  larger than a frequency estimate would (about 1/5,000). It's an inference
  semantics question, raised with the core team; it doesn't change any top-1
  prediction here.

## Reproduce

```
PYTHONPATH=. python scripts/evaluation_holdouts.py
```

Read-only; about 2,000 `_predict` calls; 20-40 minutes on shared.
