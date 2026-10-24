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
