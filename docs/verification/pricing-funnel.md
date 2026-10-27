# Verification: the Pricing tab and the Funnel (ADR 0050), on env `release3a`

Run 2026-10-27 by the author against the loaded `release3a` env (backend 8521, frontend 8520), with Playwright for the
screens and `curl` for the API. Not an independent adversary run: the failures below were found by the author's own
edge-case pass.

## Steps attempted

| Scenario | Result |
|---|---|
| Funnel and Pricing for SKU-PT-0194, today's state | renders; numbers in `docs/demo-script.md` §2b |
| Typed list price €1.75 (inside the prices tried) | funnel and Pricing move together (units +25 %, purchases +12 %) |
| Typed list price €2.60, €2.10, 1e9 (beyond the prices tried) | Pricing: "No data here"; Funnel and KPIs keep today's list price and say why (200 with `no_data`) |
| `list_price=0`, `-3`, `abc` | 422 from the query validation |
| Unknown SKU, month with no state | 404 with the message |
| `ad_level=zzz`, `discount_band=zzz`, `image_count=lots` | **found failing:** 500 on the funnel, 200 with the base rate on `image_count=lots`; **fixed:** 400 with the allowed values (a4bb8d6) |
| 40 products × (none, search ad, 4+ pictures, 20 %+ offer), now and asked | 272 funnels, purchases never above clicks; none refused |
| Whether a typed price moved the purchase estimate | **found failing:** a decimal `list_price_index` as `_predict` evidence matched only equal cents, so purchases never moved; **fixed** with `product_states.list_price_band` (dc49cca) |
| Funnel purchases against units sold | **found failing:** a quarter of the units (ranked impressions are not all showings); **fixed:** the product's own history sets the level |
| Funnel with purchases above clicks | **found failing** (62 of 272); **fixed:** purchases are clicks × `_predict purchased` given `clicked` |
| Cross-check: funnel units against `_estimate units_index` × mean units | median 0.62 over the 40 products; reported as "indicative" when more than 25 % apart |
| Pricing estimate against April's actual units, 11 products with a mean of 3+ units | aggregate calibrated (estimate 2.2 × mean against 2.24 actual); per product noisy (median estimate ÷ actual 0.74) |

## Network calls observed

`_estimate` on `monthly_sales` (`units_index`, `showings_index`, regression), `_predict` on `impressions`
(`clicked`, `purchased`, and `purchased` with `clicked: true`), `_batch` of counts on `impressions`,
`unranked_showings`, `order_lines`. The shared instance's first calls to a cold slice take about 1 s; a warm funnel is
about 400 ms in the browser header.

## Screenshots

`/tmp/wb/shots/` (session only): funnel, funnel at €1.75, Pricing at €1.75, Pricing at €2.60 (no data).

## Failures found and not fixed

- The click rate does not fall steadily with the list price across products (ADR 0050, amendment 4).
- The assumed ad spend (€180 for a banner) makes advertising a loss on any product that sells for a few euros.
- The console shows one 404 on every page, not traced (probably the favicon).
- The live `test_aito_check` tests and the numpy backtest tests cannot run in the worktree (no credentials, no numpy).
