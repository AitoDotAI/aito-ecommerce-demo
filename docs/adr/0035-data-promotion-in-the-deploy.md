# ADR 0035: The data promotion is a step of the deploy

**Status:** Accepted (2026-10-24, Antti: "review, fix and merge all on green"). Revised with aito-azure's review on 2026-10-23. The key for the cutover (§Ownership and permissions) is still Antti's open decision; the cutover isn't run until it's made.

## Context

A release that changes the data model ships in two halves:
- **the data:** a new Aito env, loaded and checked, then promoted onto
  `master`;
- **the code:** a new container image on Azure.

Today the halves are run by hand: Antti runs a promote script at night, then
the image is deployed. Neither can go first. The old code can't read the new
tables, and the new code can't read the old ones. So between the promote and
the deploy, the live demo is broken, and the gap includes precompute, which
takes minutes.

Pointing the deployed app at the new env by name (`AITO_ENV`) would remove
the promote. It's ruled out: only `master` is kept hot on shared.aito.ai,
and other envs are swapped out, so a live demo on a named env would meet
cold `_recommend` calls of 5–9 s.

## Decision

Keep the promote, and make it a step of the deploy, ordered so the live
demo is inconsistent only for the time the container takes to restart.

**Before the deploy (any time; no live impact):**
1. The release's env is loaded and checked: row counts, and
   `./do aito-check` on that env. This is what happens today
   (`observable`, `uci`).
2. **Precompute runs against the release env, writing as `master`.** The data
   after the promote are the same rows, so the snapshots are valid for
   `master`. They are committed with the release, so precompute leaves the
   cutover. This needs `./do precompute --as master`, which overrides the
   precompute store's namespace (`set_namespace` exists).
3. The image is built from the release commit.

**Staging:** the image goes to the test web app with `AITO_ENV` set to the
release env. It's slow (a cold env) but correct, and the smoke tests run
there.

**Cutover (one command in aito-azure; aito-azure's order, 2026-10-23):**
0. Print the whole plan before the first write: env, counts, backup name,
   image tags. `--dry-run` runs only the pre-flight.
1. Pre-flight, read-only: the release env exists, its row counts equal the
   release file's (`data/release-env.json`: env name, counts per table), and
   the data disk has room for the backup. On any mismatch it refuses, before
   anything is written.
2. Disk snapshot (`./do snapshot-db`, as shared releases already do). It
   covers a promote that damages master.
3. Set the new image and restart. The unified container takes about 5
   minutes to start; the old one serves old data with old code meanwhile.
4. Poll `ecommerce.aito.ai/api/version` until it reports the new build.
5. Back up `master` (`POST /_envs`, basedOn `env.master`, named
   `master-backup-<date>`), then promote the release env
   (`POST /_envs/<env>/promote`) straight away.
6. Clear the persistent cache (`./do clear-cache` against `master`), warm up
   a few representative queries (in case the promote leaves master cold),
   then run the smoke tests.

**The app waits for its data.** Between steps 4 and 5 the new code runs
against the old data. So the app reads `data/release-env.json` at startup.
Until master's tables and counts match it, data routes answer 503 ("data
release pending"), while `/api/version` and `/api/health` answer as usual.
Only once it matches does the app warm its caches. The same check repeats
every 60 seconds (see rollback). Without this, the
container's in-memory cache would hold answers warmed on the old data, and
`./do clear-cache` (another process) can't reach it.

**Rollback, data first** (aito-azure's order). The previous image may predate
the data wait: deployed first, it would warm its memory on the release's data
and keep serving it after the backup returns.
1. Promote the backup while the new image still serves.
2. Redeploy the previous image, and wait for its build on `/api/version`. It
   warms against the old data, which is master again.
3. Cache clear, warm-up, smoke tests.

During step 2 (about 5 minutes) the new code runs against the old data. So
the data wait isn't only at startup: **the app re-checks master against its
release file every 60 seconds.** On a mismatch it drops its in-memory cache
and answers 503 on data routes until the counts match again. A rollback then
shows "data release pending" for those minutes, not answers from the wrong
data.

**When a release changes no data:** the release file is unchanged, and the
cutover skips steps 1, 2, 5 and the cache clear.

## Ownership and permissions

- **This repo:** the release file, `./do precompute --as master`, and the
  checks the pre-flight runs.
- **aito-azure:** the cutover command, and running it.
- **The new permission:** the cutover needs a key that can promote over
  `master`. aito-azure proposes:
  - an ecommerce-only read-write key (or a promote-only key, if Aito has
    one), kept in Key Vault;
  - fetched by the command itself and never printed;
  - run only with Antti's yes, outside 08–10 Helsinki, announced before it
    starts, at night by preference.

  The key is Antti's decision.
- **For Aito core:** what a promote does to residency (is master hot right
  after?), and whether `basedOn` makes a full copy (disk use of backups).

## Acceptance criteria

- A release with a new env goes live with one cutover command. Old code
  never reads new data. New code reads old data only for the seconds
  between its start and the promote, answering 503 on data routes meanwhile.
- A pre-flight mismatch refuses before anything is written, and says which
  table's count differs.
- The precomputed views load from the committed snapshots right after the
  cutover, with no live `_evaluate`.
- Rollback restores the previous data and image.

## Out of scope

- Keeping several envs hot (a core capacity question).
- Releases of the other demos in the unified container. The step is generic,
  but each demo would add its own release file.
- Automatic cleanup of old envs and backups. Keep the current and previous
  ones, by hand, for now.

## Notes

### What this repo built (2026-10-24, workstream C)

- **The release file**, `data/release-env.json`: `{"env": ..., "counts":
  {table: rows}}`, written by `./do release-file <env>` from the env's
  live counts (one `_search` with `limit: 0` per table, read-only). The
  two tables the app writes while running, `prediction_cache` and
  `precompute_entries`, are not part of a release and aren't counted. The
  committed file is for env `observable`. Format and checks:
  `src/release_file.py`; a malformed file stops the app's startup.
- **The pre-flight check**, `./do release-check [<env>]`: does the env
  (default: the release file's own) hold exactly the file's tables and
  counts? Read-only. Exits 1 and prints one line per differing table
  (`orders: 11919 rows, release has 11909`, `contexts: missing ...`,
  `price_history: not in the release ...`).
- **The data wait**, `src/data_release_gate.py`. At startup and every 60 s
  the app compares the env it reads with the release file. While they
  differ, every `/api/` route except `/api/version`, `/api/health` and
  `/api/uci/*` answers 503 `{"error": "data release pending", "state",
  "release_env", "differences", "last_error"}` with `Retry-After: 60`.
  On the change to ready it warms its caches; on a change back to pending
  it drops its in-memory caches. `/api/health` carries the same status
  under `data_release`, outside its 60 s cache. Details the decision
  left open:
  - *Which env is compared:* the one the app reads, `AITO_ENV` (default
    `master`). So production compares master; staging, and local dev with
    `AITO_ENV=observable ./do dev`, compare the release env itself and
    are ready at once. A plain `./do dev` on master's old data stays
    pending, as it should.
  - *A failed read* (Aito unreachable) keeps the current state and is
    reported in `last_error`: one failed read is not evidence that the
    data changed.
  - `/api/uci/*` isn't held: it reads env `uci`, which a release of the
    pet shop's data doesn't touch.
  - The frontend needs no change: its error state shows the server's
    message, `API 503: /api/... — data release pending`.
- **`./do precompute --as master`** computes on the env `AITO_ENV` names
  and files the snapshots under master's namespace: the JSON in
  `data/precomputed/v2-master/`, and the Aito rows (keyed
  `v2@master|<view>`) in the release env's `precompute_entries`, which
  the promote carries onto master. Without `--as`, behaviour is
  unchanged.

### The commands aito-azure's cutover calls

Run from a checkout of the release commit, with the ecommerce
credentials (`./do` reads them as for any other verb).

Before the deploy (writes to the release env, not to master):

    AITO_ENV=observable ./do precompute --as master
    # commit data/precomputed/v2-master/ with the release

Cutover:

    # 1. pre-flight, read-only, also what --dry-run runs
    #    (or read env and counts from data/release-env.json directly)
    ./do release-check                  # exit 1 = refuse; names the tables
    # 4. after the new image reports its build on /api/version, it is
    #    pending: /api/health -> data_release.state == "pending"
    # 5. backup + promote (aito-azure's own calls)
    # 6. confirm master is the release, wait for the app, clear, smoke
    ./do release-check master
    # poll https://ecommerce.aito.ai/api/health until
    #   .data_release.state == "ready"   (at most ~60 s after the promote)
    AITO_ALLOW_PROD=1 ./do clear-cache
    # then the warm-up queries and the smoke tests

Rollback: after promoting the backup back, `/api/health` turns
`pending` within 60 s on the new image (data routes 503) until the
previous image replaces it.


## Amendment 2026-10-31: how often the gate reads the counts

The gate read the schema and one count per data table (about 17 calls) every 60 seconds, for every app instance, for as long as it
ran. A forgotten dev server or two added that to the shared Aito day and night. Now: every 60 seconds while the data is pending (a cutover
sees it arrive within a minute); once ready, every 15 minutes (`RELEASE_GATE_RECHECK_SECONDS`), and also when `/api/health` is polled and the
last check is over a minute old, so a deploy script watching a rollback sees it at once. `./do dev` and `./do backend-dev` set the
interval to 0: one check at startup, and none after. The cost of this: a rollback that nobody polls is noticed within 15 minutes, not 60 seconds.
