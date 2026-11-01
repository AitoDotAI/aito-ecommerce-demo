# Data release 4: the incidents and the words of feedback (ADRs 0056 and 0058)

Cut 2026-11-01 on Antti's "Can you do the data now?". The generator's switches `E1`–`E4` (a loud recall and three quiet quality problems) and `T1`, `T2`
(NPS comments, reviews that read like their stars) are on, the fixtures are regenerated, and the release is named `release4`.

## What changed in the data (seed 42)

- 3,000 customers and 658 products as before. Orders 10,594 → 10,539, order lines 36,357 → 35,972, reviews 5,202 → 5,170, NPS answers 3,204 → 3,195, recorded actions 5,626 → 5,651 (`data/release-env.json`).
- The recalled line (*PetNord Grain Free Salmon Adult Dog Food*, five SKUs, written under the house label) sells ×4 from 2025-01, goes bad in 2025-09 and 2025-10, and sells nothing from 2025-11 (it stays listed).
  Three quiet incidents hit a Sheba beef cat food line (2025-02), the house-label dog treats (2025-06 and 2025-07) and the house-label hamster food (2026-01).
- The NPS answers carry a comment (39 % do); reviews read like their stars and name the product. Ground truths are in `data/answer_key/` (`incidents.json`, `nps_comments.json`).
- Three Shop shoppers were re-picked or renumbered because the incidents change product stars and so every pick that follows: Olli is now CUST-00159, Saara has 13 orders (7 hold the bag), Eemil has 13.

## State (2026-11-01 evening)

Steps 1–5 below are done: the env `release4` exists on shared.aito.ai (a branch of master, so master is untouched), is loaded (283,274 rows, 16 tables, counts equal the release file), the snapshots are
precomputed and committed, the runs regenerated and the literal numbers updated; the full suite passes (1,111). What is left is step 6, the cutover, and it needs Antti's yes. The four `test_aito_check` snapshot tests fail when run on `release4` itself
because the snapshots are filed under master's namespace (`--as master`); they can only pass after the promote.

The churn presets of the blog's widget on the new data (read-only `_predict` on `release4`): small_animal/tampere 34.6 % (was 64.0 %), aquarium/turku 41.8 % (was 24.7 %), cat/turku 1.9 % (unchanged).

## What was not final until the data was loaded (the five red tests)

The win-back run and the stock run are built from `data/precomputed/v2-master/retention.json` and `supply.json`, which come from Aito. Until the release env is loaded and
`./do precompute` has run on it, they describe the old data. The five tests that compare them with a rebuild stay red until then.
Numbers quoted elsewhere that **will move** and must be re-read after the load: the churn probabilities of the three presets in the blog's live widget (64.0 %, 24.7 %, 1.9 %), the Customers
screenshots, `docs/demo-script.md` numbers that come from Aito (for example 2,044 of 10,594 orders hold both in the baskets), the Overview headlines.

## The steps (ADR 0035). The writes to shared.aito.ai are Antti's

1. `./do env-new release4` prints the plan (a dry run); `./do env-new release4 --apply` creates the env, a copy-on-write branch of master.
2. `AITO_ENV=release4 ./do env-load` drops and reloads every table into the env (it refuses master).
3. `./do release-check release4` (read-only): the env's row counts equal `data/release-env.json`.
4. `AITO_ENV=release4 ./do precompute --as master`: the heavy snapshots, filed as master's, written to the env and to `data/precomputed/`.
5. Then, in this branch: `./do agent-runs`, the Aito-derived numbers in the demo script, `./do check`; commit; merge.
6. The cutover (aito-azure, one command, with a backup of master): deploy the image, promote `release4` onto master, clear the cache, warm up, smoke.
