# Misplaced promotions (M1): results

Run once on 2026-11-27, 21:09Z, against the bars in
`misplaced-promotions-prereg.md` (frozen in f388bd0, amendment 1 in 562a6cd).
Judged by aito-shopify `scripts/check-misplaced-promotions.mjs` (branch
`watch/misplaced-split`, on #396's rule at f0306a7). Numbers are in
`misplaced-promotions-results.json`.

Seeds: 42, 7, 99 and the fresh 5114, 6008, 8193. 5113, 6007 and 8191 cannot be
generated on main (the incident-planner assertion), so amendment 1's rule
replaced each with the next seed that main can generate.

| id | value | bar | result |
|---|---|---|---|
| M1-0 | seeds 42 and 7, M1 off: 24 of 24 files byte-identical to main a9361ab | identical | **PASS** |
| M1-a | misplaced ÷ controls 0.846 (27 comparable product-months) | [0.9, 1.1] | **FAIL** |
| M1-b | working ÷ controls 1.314 (1,501) | ≥ 1.2 | PASS |
| MW-1 | misplaced "Sure (higher)" 0.0 % (26 judged) | ≤ 5 % | PASS |
| MW-2 | misplaced "Sure or Likely (higher)" 7.7 % (26) | ≤ 15 % | PASS |
| MW-3 | working minus misplaced, any higher: 14.5 points (1,454 working) | ≥ 5 points | PASS |

Controls: 3,017 full-price product-months, geometric mean 1.176; Margin watch
refused 3 of 48 months (fewer than 30 controls).

Not fixed or re-run after seeing this. What the numbers show (observations,
not a diagnosis):
- Only 27 of the misplaced SKUs' offer months are comparable in six seeds
  (about 4–5 per seed over 8 months): most of the drawn SKUs sell under 10
  units a month (MIN_CELL), so Margin watch rarely sees them.
- The misplaced products sold a smaller share on offer than the controls
  did. Likely causes (not tested): the working offers in their category take
  demand from them, and the controls drift upward (1.176).
