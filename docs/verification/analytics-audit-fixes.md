# Verification: analytics audit fixes (PR #200)

**Manual and local.** Written by hand on 2026-11-18, not produced by `./do verify`, which is not wired (it exits 1). Everything ran against a local engine built from source (aito-core worktree `13e3fef250`, port 9031, no shared host). The Aito Python client and the app were pointed at it by environment set inside the run scripts.

## What the PR changes

| Commit | Change |
|---|---|
| `81423cd` | Acquisition, "What the first basket says": the threshold line shows the number of candidates tested and the real z, not the number of rows shown. |
| `0fd012a` | Customers: the profit footnote's cost facts (kept lines, lines sold below cost, unit cost as a share of list price) come from `summary.json`, computed from the fixtures, not hard-coded. |
| `5cc552d` | Customers: the footnote read "34,955kept lines"; a space was missing. The sentence is built in `frontend/lib/cost-footnote.ts` and tested without a browser. |

## Local gate

| Step | Result |
|---|---|
| Python tests, every file except the three live ones | 1233 passed, 7 skipped (run on `0fd012a`) |
| `tsc --noEmit` | clean (after `5cc552d`) |
| Frontend node tests | 17 of 17 pass after `5cc552d` (15 before; the two new ones fail with the old text: "of 34,955kept lines") |
| Browser read, Acquisition (local app, local engine, release gate forced ready for that process only) | "13 lifts had >= 30 independent rows and were tested ... z = 2.89" beside 1 row shown (run on `0fd012a`) |
| Browser read, Customers | page loads; footnote read "169 of 34,955kept lines" (run on `0fd012a`), which `5cc552d` fixes |

## SKIPPED

- `tests/test_claims_live.py`, `tests/test_live_smoke.py`, `tests/test_aito_check.py`: they call the shared host.
- `./do aito-check` and `./do verify-demo` against a live deployment.
- `./do verify <feature>`: not wired.
- A browser re-read of the Customers footnote after `5cc552d`: no engine was running by then. The text is covered by the node test; `tsc` compiles the page's import.

## Not part of the PR: the v2 SQL check for the Overview headlines

Run the same day on the same local engine, to settle whether the Overview's numbers can move from Python paging into SQL (`docs/notes/2026-11-18-analytics-from-aito-audit.md`, row 2). `POST /api/v2/_sql` takes the raw SQL as the body (`text/plain`). Python over every paged order and line row, against SQL, cell by cell:

| Cells | Python | SQL | Equal |
|---|---|---|---|
| Orders per month and revenue per month, 24 months | `shop_totals` | `SELECT month, count(*), sum(total_eur) FROM orders GROUP BY month` | 25 of 25 (24 month cells of orders and revenue, plus the month count) |
| Orders, last 12 months (2025-05 to 2026-04) | 8,449 | `count(*) ... WHERE month >= '2025-05'` | yes |
| Revenue, last 12 months | 668,938.92 | `sum(total_eur) ...` | yes |
| Average basket | 79.17 | `sum(total_eur) / count(*)` | yes |
| Customers ordering | 2,833 | `count(DISTINCT customer_id)` | yes |
| Units per product since 2025-05, all 630 SKUs | Counter | `SELECT product_sku, sum(qty) FROM order_lines WHERE order_id.month >= '2025-05' GROUP BY product_sku` | yes |
| Top 5 units | `most_common(5)` | the five largest of the 630 groups | yes |

Total: **31 of 31 compared cells equal**: 25 for the months, 4 headline numbers, 2 for units per product (all SKUs, and the top five). A month is one cell holding orders and revenue. Script: `overview_sql_proof.py` in the session scratchpad; not committed.

### Two engine gaps found (on E7, `td-20261117223416558306`)

1. **`ORDER BY` an aggregate fails**, by alias or expression: `SELECT product_sku, sum(qty) AS u FROM order_lines GROUP BY product_sku ORDER BY u DESC LIMIT 5` answers `query.invalid`: "format query: field 'field' must be of type 'string'". The unaliased `ORDER BY sum(qty)` is a parse error. The best sellers therefore group every SKU (630 rows) and rank in the app.
2. **Subqueries** answer "SQL parse error: subqueries are not supported yet", so "orders since month X" cannot be a nested `IN (SELECT ...)`; the link-path filter (`order_id.month`) is the working form.

Untested here: whether the demo's served engine (shared master) answers `_sql` the same way; this was the local build.
