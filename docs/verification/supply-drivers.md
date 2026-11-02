# Verification: do the drivers of demand improve Supply's estimates? (ADR 0061)

**Run:** 2026-11-02. `scripts/supply_drivers_backtest.py` (Aito `_evaluate`, read-only) and `scripts/supply_unit_error_backtest.py` (offline). Both are repeatable.

## 1. The range forecast with the product's state and season

Seven test months (October 2025 to April 2026), each trained only on months before it; accuracy of the sales range, pooled over 4,586 product-months (the Model checks page's test):

| Conditions | Accuracy |
|---|---|
| "Same range as last month" | 39.4 % |
| Last month's range, the season, the category and the product's stars band and age | 41.1 % |

Difference **+1.7 pp [−0.3, +3.7]**: a tie. The first fair try is ahead in most months and not clearly ahead overall. Earlier attempts that looked worse included the product id or the
state's own id (unique per product-month) or trained on later months as well as earlier ones (the latter flattered the model; it is not used).

## 2. The reorder list's unit estimate with a driver adjustment

The gate in the ADR: move the reorder list off the observed three-month rate only if an adjustment beats it on units by absolute error. A factor per group, fitted only on earlier months:

| Adjustment | Mean absolute error against the plain rate |
|---|---|
| By stars band | +0.012 ± 0.045 units: no clear difference |
| By stars band and age | −0.023 ± 0.061: no clear difference |
| By stars band and season | +0.029 ± 0.049: no clear difference |

The stars band does move next month's sales on average (a 1–2 star product sells 0.93 of its recent rate next month, a 5-star one 1.24), but the product-to-product noise is far larger than
that shift, so the adjusted estimate is no better per product. **The reorder list keeps observed sales** and says so.

## Reading

- The drivers carry real signal at the group level (the stars band above) and the range forecast with them reaches the simple rule; in this simulated data they do not beat it for a per-product quantity.
- Seasonal ware is represented only through the season and the product's own year-ago months (the second lever uses it); the catalogue has little that is strongly seasonal, so adding such products is a data change, not tested here.
