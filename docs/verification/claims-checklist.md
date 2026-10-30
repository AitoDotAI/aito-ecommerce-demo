# Claims checklist: every number a visitor reads, and where it comes from

**Written:** 2026-10-30, on release 3b (served as `v2@master`). Status columns are as read that day.
A claim is a number or a comparison in the README, the UI copy (`frontend/`) or the demo script. Each row says where it is
stated, where it comes from, and the test that recomputes it. `tests/test_claims.py` reads committed files and constants;
`tests/test_claims_live.py` asks a running app (needs Aito). A claim whose source is a past measurement says
which release that measurement was made on.

## README

| # | claim | source | release | test | status |
|:--|:--|:--|:--|:--|:--|
| R1 | 658 products … 5,626 recorded actions (README:169-171) | `data/release-env.json` `counts` | 3b | `test_readme_row_counts_are_the_releases` | ok |
| R2 | `"api": "v2@observable"` (README:174) | `GET /api/version` on prod answers `v2@master` | 3b | `test_readmes_version_example_names_the_env_a_promoted_release_serves` | **FAILS** (stale example) |
| R3 | sandbox branch "deleted after 3 hours" (README:129) | `src/sandbox_envs.py` `MAX_AGE` | any | `test_readme_sandbox_branch_lives_as_long_as_the_code_lets_it` | ok |
| R4 | a lever writes "May 2026" (README:130) | `src/demand_forecast.py` `FORECAST_MONTH` | 3b | `test_readme_names_the_month_a_lever_writes` | ok |
| R5 | the sandbox Shop re-scores its "top 40" (README:132) | `src/shop_rescore.py` `RESCORED` | any | `test_readme_says_how_many_cards_the_sandbox_shop_re_scores` | ok |
| R6 | 31 % against 15 % on UCI (README:48-50) | 197 of 636 and EASE 98 of 636 (`tests/test_backtest_uci_reproduction.py`, `uci-check`) | UCI, real data | `test_the_uci_claim_is_what_its_counts_round_to` | ok (the counts' own tests need `data/uci/`, skipped without it) |
| R7 | "5–7 minutes" walkthrough (README:19) | the demo script's own timings | none | none | **unverified**: a duration, not a measured number; the script header says 6–8 minutes, so the two disagree |

## UI copy

| # | claim | where | source | test | status |
|:--|:--|:--|:--|:--|:--|
| U1 | 31 % / 15 % claim | `components/business-reorders/ClaimBox.tsx:8` | as R6 | `test_the_uci_claim_is_worded_the_same_wherever_it_is_quoted` | ok |
| U2 | "tested at 5–20 % off", "a quarter (13 weeks)", "even at 20 % off" | `app/supply/page.tsx:81,118` | `src/markdown_proposal.py` `DISCOUNT_LEVELS_PCT`, `HORIZON_WEEKS` | `test_supply_says_the_markdown_range_and_horizon_the_code_tests` | ok |
| U3 | "30 or more" independent rows, "95 %" family interval | `lib/panel-content.ts:175` | `src/price_bands.py` `MIN_SWEET_SPOT_SUPPORT`, `src/lift_rows.py` `FAMILY_CONFIDENCE` | `test_the_lift_panel_says_the_support_and_confidence_it_requires` | ok |
| U4 | the held-out sweeps' result, on which release | `components/shop/ShopSettings.tsx:74` | `docs/verification/last-basket-prereg.md` | `tests/test_shop_claims_are_traceable.py` (branch `traceable-shop-claims`) | ok after that branch; not re-measured on 3b |
| U5 | order count in the Aito panel | `components/shell/AitoPanel.tsx` | read from `/api/overview`, not typed | none needed | computed, not stated |
| U6 | band labels "10–15 % off", "15–20 % off", "20 % or more off" | `components/product/labels.ts` | `src/price_bands.py` bands | none yet | **unverified**: labels are text; the bands are `10-15`, `15-20`, `20+` and agree by eye |

## Demo script (`docs/demo-script.md`)

| # | claim | source | release it says | test | status |
|:--|:--|:--|:--|:--|:--|
| D1 | Supply: 83 now, €10,272, 664 units, €9,924 at cost; €27,566 in 79; 14 won't clear (:64-65) | `data/precomputed/v2-master/supply.json` | 3b | `test_the_demo_scripts_supply_headline_numbers_are_the_snapshots` | ok |
| D2 | "the page shows 730 units" (:70) | the same snapshot: 664 units | 3a | `test_the_demo_scripts_check_first_line_agrees_with_its_own_table` | **FAILS** (release 3a's figure, and the table above it says 664) |
| D3 | "81 % of customers" (:49) | `docs/verification/action-recovery.md` | 3b | `test_the_demo_script_quotes_the_recovery_rate_the_report_gives` | ok |
| D4 | Product decision: 20.0 % → 31.5 % (×1.57) (:100) | `GET /api/product?sku=SKU-PT-0563&month=2026-04` → 12.9 % → 20.4 % (×1.58) | 3a | `test_the_scripts_decision_row_is_what_the_product_view_leads_with` | **FAILS** |
| D5 | Margin per 100 showings €201.02 → €228.10 (+13 %), break-even ×1.38 (:101) | the same: €129.80 → €147.94 (+14 %), ×1.38 | 3a | `test_the_scripts_margin_row_is_the_decisions_margin_per_100_showings` | **FAILS** (break-even alone still holds) |
| D6 | Funnel today 10.6 showings → 6.8 clicks → 5.6 purchases … profit €8.58 (:114) | `GET /api/product/funnel?sku=SKU-PT-0194&month=2026-04` → 9.6 → 5.7 → 4.0, profit €6.44 | 3a | `test_the_scripts_funnel_row_is_the_funnel_today` | **FAILS** |
| D7 | Pricing: best €1.59 list, €8.27 a month (:116) | `GET /api/product/pricing?…` → €1.59, €7.62 | 3a | `test_the_scripts_pricing_row_names_the_most_profitable_price` | **FAILS** (the price holds, the profit does not) |
| D8 | Shop kit path: Trixie Hideout small 22.5 %, medium 18.9 %, Exercise Wheel 16.1 %, PetNord Hideout 10 % (:171) | `GET /api/shop/suggestions?shopper=paivi&month=2026-04` → PetNord Hideout 22 %, Exercise Wheel 18.4 %, Trixie medium 18 %, small 12.7 % | 3a | `test_the_scripts_kit_path_is_the_order_and_percentages_the_shop_shows` | **FAILS** (a different order) |
| D9 | Buy again: Guinea Pig Mix Food 15kg, 67 % (:172) | the same endpoint | 3b | `test_the_scripts_buy_again_card_is_the_one_the_shop_shows` | ok |
| D10 | Patterns: dog dry food + dental treats 3.11× (2.70–3.57), 64 % / 96 %, 2,168 of 10,894 (:313-315) | `GET /api/shop-analytics/baskets` → 3.17× (2.75–3.66), 64 % / 96 %, 2,044 of 10,594 | 3a | `test_the_scripts_dog_food_and_dental_treats_numbers_are_the_patterns_views` | **FAILS** |
| D11 | UCI row: 31 %: 197 of 636, 15.4 % EASE (:274-275) | as R6 | UCI | `test_the_demo_scripts_uci_row_gives_the_same_counts` | ok |

## Not yet covered (stated in the demo script, no lookup written)

These are release 3a figures the script itself says must be re-read before a partner demo. Each needs either a sandbox run
(marked **(Sunday)** in the script) or a lookup like D4–D10:

- The `$why` chain for Trixie Hideout (:102: 14.3 % × 1.38 × 1.63 × 0.98 = 31.5 %), the 20 %+ row (:139: 32.7 %, ×1.63, lift 1.44), the May decision (:140: €164.23 → €228.10), the pushback sentence (:143-144: 32.7 % against 31.5 %).
- The Pricing tab's units (:116: 8.0 → 10.0, +25 %), the cross-check (:117), the funnel at €1.75 (:115), the price range paid (:119: €1.41–€1.90), and the advertising assumptions (:120: €60, €180).
- The Shop's "Before the lever" card (:188: 57 %), the May row quoted by the agent (:252-253).
- The patterns row on offers (:316: 1.42×, [1.30, 1.54], 2,602 of 6,276) and the 6 % held-out figure (:295-297).
- The Evidence model checks the script cites.

## How to read a failure

A failure in `tests/test_claims*.py` means the page says one number and its source says another. The fix is to change the page, or, if the source is wrong, the source: never the test. A claim that moves to a new release gets a new row, not an edited one.
