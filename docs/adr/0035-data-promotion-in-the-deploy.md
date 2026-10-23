# ADR 0035: The data promotion is a step of the deploy

**Status:** Proposed (2026-10-23)

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

**Cutover (one command in aito-azure, back to back):**
1. Pre-flight: the release env exists, and its row counts equal the counts
   the release declares (a file in the release, e.g.
   `data/release-env.json`: env name plus counts per table). On any
   mismatch it refuses, before anything is written.
2. Back up `master` (`POST /_envs`, basedOn `env.master`, named
   `master-backup-<date>`).
3. Promote the release env (`POST /_envs/<env>/promote`).
4. Set the image and restart the web app (today's deploy step).
5. Clear the lazy cache (`./do clear-cache` against `master`).
6. Smoke tests on prod, as today.

**Rollback:** promote the backup, then redeploy the previous image.

**When a release changes no data:** the release file names no env, and the
cutover skips steps 1–3 and 5.

## Ownership and permissions

- **This repo:** the release file, `./do precompute --as master`, and the
  checks the pre-flight runs.
- **aito-azure:** the cutover command, and running it.
- **The new permission:** the deploy now holds a key that can promote over
  `master` on shared.aito.ai. Today only Antti runs such writes. Which key,
  where it's stored, and who may run the cutover is Antti's decision.

## Acceptance criteria

- A release with a new env goes live with one cutover command. The live
  demo answers from the new data with the new code, and the gap is the
  restart.
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
