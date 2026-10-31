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
| R2 | `"api": "v2@observable"` (README:174) | `GET /api/version` on prod answers `v2@master` | 3b | `test_readmes_version_example_names_the_env_a_promoted_release_serves` | fixed 2026-10-30 (was: stale example) |
| R3 | sandbox branch "deleted after 3 hours" (README:129) | `src/sandbox_envs.py` `MAX_AGE` | any | `test_readme_sandbox_branch_lives_as_long_as_the_code_lets_it` | ok |
| R4 | a lever writes "May 2026" (README:130) | `src/demand_forecast.py` `FORECAST_MONTH` | 3b | `test_readme_names_the_month_a_lever_writes` | ok |
| R5 | the sandbox Shop re-scores its "top 40" (README:132) | `src/shop_rescore.py` `RESCORED` | any | `test_readme_says_how_many_cards_the_sandbox_shop_re_scores` | ok |
| R6 | 31 % against 15 % on UCI (README:48-50) | 197 of 636 and EASE 98 of 636 (`tests/test_backtest_uci_reproduction.py`, `uci-check`) | UCI, real data | `test_the_uci_claim_is_what_its_counts_round_to` | ok (the counts' own tests need `data/uci/`, skipped without it) |
| R7 | "6–8 minutes" walkthrough (README:19) | the demo script's own title | none | none | README now matches the script's title; a duration, not a measured number (no timed run) |

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
| D1 | Supply: 83 now, €13,200 if May sells like the last three months, 839 units, €11,832 at cost; €27,566 in 79; 14 won't clear (:64-65) | `data/precomputed/v2-master/supply.json` | 3b | `test_the_demo_scripts_supply_headline_numbers_are_the_snapshots` | ok |
| D2 | "the page shows 730 units" (:70) | the same snapshot: 664 units | 3a | `test_the_demo_scripts_check_first_line_agrees_with_its_own_table` | fixed 2026-10-30 (was: release 3a's figure, and the table above it says 664) |
| D3 | "81 % of customers" (:49) | `docs/verification/action-recovery.md` | 3b | `test_the_demo_script_quotes_the_recovery_rate_the_report_gives` | ok |
| D4 | Product decision: 20.0 % → 31.5 % (×1.57) (:100) | `GET /api/product?sku=SKU-PT-0563&month=2026-04` → 12.9 % → 20.4 % (×1.58) | 3a | `test_the_scripts_decision_row_is_what_the_product_view_leads_with` | fixed 2026-10-30 |
| D5 | Margin per 100 showings €201.02 → €228.10 (+13 %), break-even ×1.38 (:101) | the same: €129.80 → €147.94 (+14 %), ×1.38 | 3a | `test_the_scripts_margin_row_is_the_decisions_margin_per_100_showings` | fixed 2026-10-30 (was: break-even alone still holds) |
| D6 | Funnel today 10.6 showings → 6.8 clicks → 5.6 purchases … profit €8.58 (:114) | `GET /api/product/funnel?sku=SKU-PT-0194&month=2026-04` → 9.6 → 5.7 → 4.0, profit €6.44 | 3a | `test_the_scripts_funnel_row_is_the_funnel_today` | fixed 2026-10-30 |
| D7 | Pricing: best €1.59 list, €8.27 a month (:116) | `GET /api/product/pricing?…` → €1.59, €7.62 | 3a | `test_the_scripts_pricing_row_names_the_most_profitable_price` | fixed 2026-10-30 (was: the price holds, the profit does not) |
| D8 | Shop kit path: Trixie Hideout small 22.5 %, medium 18.9 %, Exercise Wheel 16.1 %, PetNord Hideout 10 % (:171) | `GET /api/shop/suggestions?shopper=paivi&month=2026-04` → PetNord Hideout 22 %, Exercise Wheel 18.4 %, Trixie medium 18 %, small 12.7 % | 3a | `test_the_scripts_kit_path_is_the_order_and_percentages_the_shop_shows` | fixed 2026-10-30 (was: a different order) |
| D9 | Buy again: Guinea Pig Mix Food 15kg, 67 % (:172) | the same endpoint | 3b | `test_the_scripts_buy_again_card_is_the_one_the_shop_shows` | ok |
| D10 | Patterns: dog dry food + dental treats 3.11× (2.70–3.57), 64 % / 96 %, 2,168 of 10,894 (:313-315) | `GET /api/shop-analytics/baskets` → 3.17× (2.75–3.66), 64 % / 96 %, 2,044 of 10,594 | 3a | `test_the_scripts_dog_food_and_dental_treats_numbers_are_the_patterns_views` | fixed 2026-10-30 |
| D11 | UCI row: 31 %: 197 of 636, 15.4 % EASE (:274-275) | as R6 | UCI | `test_the_demo_scripts_uci_row_gives_the_same_counts` | ok |

| D12 | Why chain 14.0 % × 1.32 × 1.11 × 1.00 = 20.4 %, shown 8 (0 bought) / 7 (4 bought) (:102) | `GET /api/product?sku=SKU-PT-0563…` `discount.bands` | 3b | `test_the_scripts_why_chain_multiplies_out_the_offer_bands_factors` | ok |
| D13 | The 20 %+ row: 22.3 %, ×1.72, band lift 1.44, shown 7 (4 bought) (:139) | the same | 3b | `test_the_scripts_20_percent_row_is_the_bands_numbers` | ok |
| D14 | The pushback: "sells about as well" (22.3 % against 20.4 %) (:143-144) | the same; the test also fails if the two drift more than 5 points apart | 3b | `test_the_pushback_still_holds_at_20_percent_off_it_sells_about_as_well_as_at_10_15` | ok |
| D15 | Before the lever: the hideout is the 2nd card, 56 % (:188) | `GET /api/shop/grid?…&recent=cart` (the page's own default) | 3b | `test_the_scripts_before_the_lever_row_is_where_the_hideout_stands_in_picked_for_you` | ok, **story changed** (below) |
| D16 | Public Shop: Picked for you leads with Trixie Hideout, medium, 58 %, ★ 5 (:228) | the same | 3b | `test_the_scripts_public_shop_line_names_the_card_picked_for_you_leads_with` | ok |
| D17 | Kit narration names the leader: "the PetNord Hideout leads, then PetNord Exercise Wheel and the Trixie hideouts" (:174-176) | `GET /api/shop/suggestions?shopper=paivi…` `next_for_pet` | 3b | `test_the_scripts_narration_names_the_product_the_kit_path_leads_with` (also fails if the leader stops being a hideout) | ok |
| D18 | Presenter note: "0 of 8 is the observed count at 10–15 %; 20.4 % is the model's shop-wide lift" | the discount bands | 3b | `test_the_scripts_presenter_note_gives_the_observed_count_beside_the_models_rate` | ok |
| D19 | Read back: "May 2026, 20 % or more off, €17.27, 4 stars"; list price €22.28 at a typical 22.5 %; 4 stars (1 review) (:140, :213, :254) | `/api/product` margins and state; `reviews` count | 3b | `test_the_scripts_read_back_row_is_the_levers_price_and_the_products_stars` | ok (was "5 stars (1 review)", release 2/3a) |
| D20 | Offers over-represented in purchases: 1.41× [1.29, 1.53], 2,518 of 6,069 rows (:318) | `GET /api/shop-analytics/funnel?kpi=purchased` | 3b | `test_the_scripts_offers_row_is_the_lift_of_products_on_offer_in_purchases` | ok (was 1.42× [1.30, 1.54], 2,602 of 6,276) |
| D21 | Advertising assumptions: none, search €60, banner €180 a month (:122) | `src/product_funnel.py` `AD_SPEND_EUR` | any | `test_the_demo_scripts_advertising_assumptions_are_the_funnels` | ok |
| D22 | "within 6 %" of what shoppers then did, on 56,005 held-out impressions (:296) | `docs/aito-cheatsheet.md` "A discount band as a what-if", measured on release 2 (117,026 impressions) | 2 | `test_the_held_out_calibration_figure_says_which_release_it_was_measured_on` | **not re-measured on 3b**: the line now says so. A re-run needs about 2,600 nested-`from` predicts on the shared instance |

**Where the story changed, not only the numbers (2026-10-30).** On 3a the Trixie Hideout, small led the kit path (22.5 %) and was the 3rd "Picked for you" card; on 3b it is 4th in the kit path (12.7 %, behind PetNord Hideout, PetNord Exercise Wheel and Trixie Hideout, medium) and 2nd in "Picked for you". The kit line, "Shoppers who owned a cage and a bottle bought a hideout next", still holds (a hideout leads), and the lever's discounted product still rises. The narration now names the actual leader (the PetNord Hideout) and a test pins it (D17), and the script no longer says the hideout rises "to first" (it is 2nd today; the rank after the lever is read in the sandbox). The Why row's basis reads "at 10–15 % it was shown 8 times (0 bought)", and a presenter note beside it (D18) says the 0 of 8 is the observed count and the 20.4 % is the model's shop-wide lift.

## Not yet covered

- **Sandbox rows marked (Sunday)** (:141, :149, :153, :189, :190, :212, :253): they carry no figure, or a figure only a sandbox run reads (May's units and profit, the offer factor, the re-scored rank). Making a sandbox is a copy-on-write branch on the shared sandbox database, so a run is Antti's call; until then each says it is read in the sandbox.
- The model checks the script cites (section 6), beyond the UCI row, and the Evidence figures: the Model checks page reads `data/evidence/model-checks.json`, which `tests/test_aito_check.py` compares with a live run on the `snapshot-drift-check` branch.
- The 6 % calibration figure (D22) is labelled, not recomputed.

## How to read a failure

A failure in `tests/test_claims*.py` means the page says one number and its source says another. The fix is to change the page, or, if the source is wrong, the source: never the test. A claim that moves to a new release gets a new row, not an edited one.
