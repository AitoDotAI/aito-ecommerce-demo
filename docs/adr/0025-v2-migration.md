# ADR 0025: Migrate to Aito API v2 (Rep2), staged in a separate env

**Status:** Proposed
**Date:** 2026-08-27
**Deciders:** Antti

## Context

Aito is shipping a new storage/examination engine — **Rep2** (`CollectionDb`)
— and a new REST surface, **API v2** (`/api/v2/_predict`, `_recommend`,
`_search`, …). Every demo in the fleet is being migrated onto `/api/v2`, using
the demo's real query payloads as a live conformance probe: each place the demo
breaks on v2 is filed as an aito-core gap. This ADR covers the ecommerce demo's
migration.

The migration is non-obvious in two ways:

1. **We must not disturb the running demo.** `ecommerce.aito.ai` and every
   local checkout point at the same shared instance
   (`https://shared.aito.ai/db/aito-ecommerce-demo`), and the Layer-2
   prediction cache is a table *on that instance*. Experimental v2 queries and
   a differently-typed schema cannot be run against the live data.
2. **v1 and v2 return different response shapes and different ML values.** The
   app is written against v1 field names; naively pointing it at v2 yields
   `undefined` at the point of use (silent, since both versions answer `200`),
   and the predicted numbers themselves differ between engines.

The sibling **aito-demo** repo has already completed this migration
(`docs/rep2-migration.md`, `npm run v2:parity` → 0 breaks). We adopt its
proven pattern rather than inventing our own.

## Aito usage

Staging uses the **Aito envs** feature
(<https://aito.ai/docs/api/envs/>): one Aito instance hosts multiple named
envs. We keep the default `master` env on Rep1 / v1, and stage v2 in a new env
cloned from it — same instance, same API key, isolated data and cache.

Create the env (once), then upload a collection-typed schema + identical data:

```jsonc
// POST https://shared.aito.ai/db/aito-ecommerce-demo/api/v1/_envs
{ "name": "v2", "basedOn": "env.master" }
```

```jsonc
// PUT  .../env/v2/api/v2/schema/products
// schema-v2.json — every table "type": "collection" (vs "table" on v1)
{ "type": "collection", "columns": { /* … identical to schema.json … */ } }
```

Named envs are addressed with an `/env/<name>` prefix; `master` is unprefixed.
So the four query families the demo uses move as:

| v1 (today)                                            | v2 (staged)                                                        |
|:------------------------------------------------------|:------------------------------------------------------------------|
| `…/db/aito-ecommerce-demo/api/v1/_recommend`          | `…/db/aito-ecommerce-demo/env/v2/api/v2/_recommend`               |
| `…/api/v1/_search` · `_predict` · `_aggregate` · `_relate` | `…/env/v2/api/v2/_search` · `_predict` · `_aggregate` · `_relate` |

## Decision

Mirror aito-demo. Route **every** Aito call through one configurable base path
and normalise v2 responses back to v1 field names at the single transport
chokepoint, so the service modules and cache stay unchanged.

1. **One switch, one base path.** Replace the hardcoded `/api/v1{path}` in
   `AitoClient._url` (`src/aito_client.py:54`) with a base assembled from
   config:

   ```
   base = f"{aito_api_url}{env_path}/api/{api_version}"
   #   v1/master → https://shared.aito.ai/db/aito-ecommerce-demo/api/v1
   #   v2/v2 env → https://shared.aito.ai/db/aito-ecommerce-demo/env/v2/api/v2
   ```

   Driven by an env var (`AITO_USE_V2=1`), defaulting off. `AITO_ENV`
   overrides the env name for feature-branch sandboxes. No module may
   reintroduce a literal `/api/v1/` — that silently opts its call out of the
   toggle.

2. **v2 → v1 normalisation in the client.** Port aito-demo's `aito-compat.js`
   to a small `src/aito_compat.py`, applied inside `_request` before the
   response reaches any service. It is **additive and structural** — it aliases
   v2 names to v1 names without discarding the v2 names, and detects shapes
   (e.g. the `{kind, data}` envelope) structurally rather than by endpoint
   name. Known transforms to port (measured by aito-demo):

   | What | v1 | v2 | Handling |
   |:--|:--|:--|:--|
   | `_aggregate`/`_estimate`/`_evaluate` envelope | bare | `{kind, data}` | unwrap |
   | predict hit value | `feature` | `$value` | alias |
   | predict hit `field` | present | absent | restore from request |
   | non-exclusive predict | `exclusiveness: false` | `field.$feature` | rewrite request |
   | `_relate` argument | `"field"` / `{obj}` | `["field"]` | send array form (valid on both) |
   | `related` value | `{$has: v}` | sometimes bare `v` | wrap |
   | `$matches` in `select` | ok | 400 | drop (nothing reads it) |

3. **Env setup + parity as `./do` verbs.**
   - `./do v2-env` — create the `v2` env and upload `schema-v2.json` + fixtures
     (the analogue of `upload-data-v2.js`). Refuses to run against the shared
     `master` addressing; prints its target via `_show_target`.
   - `./do aito-check --v2` (parity) — replay every demo query body against
     **both** envs and diff the normalised payloads, à la aito-demo's
     `v2:parity`. The captured run lands in `docs/verification/v2-parity.json`.
   - `_show_target` learns to surface the env (`env=v2`) alongside the URL.

4. **Default stays v1.** `ecommerce.aito.ai` keeps serving `/api/v1` against
   `master`. Flipping the default is a **separate** decision (see Out of
   scope): the app runs on v2, but v2 returns different ML values, which
   changes what the demo shows.

5. **File breaks as core gaps, don't work around.** Per CLAUDE.md Prime
   Directive #2, a v2 divergence that is an engine defect (not a response-shape
   rename) is filed against aito-core and referenced here — never silently
   patched. aito-demo already surfaced two we expect to re-hit: the
   `_estimate` default-KNN model diverging from v1 (open core ticket) and
   `exclusiveness:false` 400ing on v2.

## Acceptance criteria

- [ ] With `AITO_USE_V2=1`, every demo view renders against the `v2` env — no
      `/api/v1` call escapes the toggle (asserted by a lint test, as in
      aito-demo's `v2-compat-lint`).
- [ ] With the toggle unset, the demo behaves exactly as today against
      `master` / v1.
- [ ] `./do v2-env` creates the env from `env.master` and uploads the
      collection-typed schema + fixtures, printing a non-shared target.
- [ ] `./do aito-check --v2` replays every query family against both envs and
      reports each divergence as either a normalised-away shape difference or a
      filed core gap — no unexplained breaks.
- [ ] `master` / v1 and the live cache are provably untouched by any v2 verb.
- [ ] Each engine-level divergence found has a linked aito-core gap ticket.

## Demo impact

None to the live demo path in this ADR — the default stays v1, so
`docs/demo-script.md` is unchanged and every demo moment is preserved. The v2
env is a staging surface reached only via `AITO_USE_V2=1`. Flipping the public
default to v2 is a follow-up ADR that will re-verify each demo moment against
the v2 ML values first.

## Out of scope

- **Flipping the production default to v2.** Separate ADR, gated on parity +
  a demo-moment re-verification against v2's ML values.
- **Fixing the core gaps** the migration surfaces (e.g. `_estimate` KNN
  divergence). Those are aito-core tickets; this repo only files and references
  them.
- **Multi-env routing at runtime.** One env per process, chosen at startup by
  env var — no per-request env selection.
- **Precompute/cache changes.** The precompute-and-serve store (ADR 0024) and
  the two-layer cache keep working unchanged against whichever env is targeted.

## Consequences

**Good:**
- The demo becomes a live v2 conformance probe with a repeatable parity check.
- Prod is structurally safe — separate env, separate cache, default unchanged.
- One chokepoint (`AitoClient`) carries all version differences; service
  modules and the frontend stay written against v1 names.
- We inherit aito-demo's measured gap list instead of rediscovering it.

**Bad:**
- A compat layer is indirection a reader must understand; mitigated by keeping
  it small, additive, and thoroughly commented (it doubles as documentation of
  the v1↔v2 differences).
- The `v2` env must be recreated if fixtures change (`./do v2-env` handles it).
- Parity only covers query shapes the demo actually issues — genuinely novel
  v2 behaviour outside those shapes is out of view (noted, not silently
  assumed covered).

## Notes

- Company AI ticket: `td-20260815095525226038` — "[aito-ecommerce-demo]
  Migrate the ecommerce demo onto /api/v2, filing each break as a core gap".
- Reference implementation: `aito-demo/docs/rep2-migration.md`,
  `src/config.js`, `src/aito-compat.js`, `scripts/v2-parity.js`.
- Aito envs: <https://aito.ai/docs/api/envs/>.
- Related open core gaps to link as we hit them: `_estimate` default-KNN
  divergence (`td-…125635040997`), `recommend` disjunctive-filter drop / V2-13,
  `_match` raw counts / V2-12.
- Open question: aito-demo shares one instance for both envs. Confirm the
  shared instance's env quota/storage headroom before creating `v2`, or stage
  on a dedicated instance if headroom is tight.

## Corrections from implementation (2026-09-09)

Three claims above did not survive contact with a real env. Recorded here
rather than edited away, because each one is a trap the next demo will hit.

1. **The clone brings the data — there is no upload step.**
   `basedOn: env.master` is copy-on-write over the tables *and* their rows
   (verified: `products` 658, `impressions` 125 935, `orders` 12 215 present
   immediately). The `PUT .../schema/{table}` this ADR describes fails with
   `schema.create_failed: Table 'products' already exists`, and there is no
   analogue of aito-demo's `upload-data-v2.js` to write.

2. **What makes a table "v2" is its `engine`, not its schema `type`.**
   `/api/v2` is *engine-dispatched*: a table still on `engine: v1` served over
   `/api/v2` runs the v1 **adapter**, so pointing the demo at v2 without
   migrating exercises the compatibility path and proves almost nothing. The
   real step — and the real customer migration path, "migrate the storage,
   change no application code" — is:

   ```
   POST {url}/env/v2/api/v2/schema/{table}/_migrate   {"engine": "v2"}
   ```

   It is idempotent (a second call answers `status: unchanged`) and
   **irreversible**: there is no reverse migration. Safe here only because it
   happens in a cloned env — `master` is untouched, and the env can be dropped
   with `DELETE {url}/api/v1/_envs/v2` and re-cloned.

3. **`_recommend` on a link column does not auto-expand the linked row on v2.**
   Same body, same data:

   | | v1 | v2 |
   |:--|:--|:--|
   | hit keys | `$p`, `sku`, `name`, `pet_type`, `brand`, `price_eur`, … | `$p`, `$value` only |

   v1 expands every column of the linked table by default; v2 returns the bare
   id in `$value`. This is a **default** difference, not a missing capability —
   `select: ["$p", "$value", "name", "pet_type"]` returns the columns
   flattened, exactly as v1 did implicitly. (`select: [{"product_sku": [...]}]`
   is rejected: `unsupported value START_ARRAY`.)

   It is silent and severe: every caller reading `hit["name"]` /
   `hit["pet_type"]` — Smart Search, For You, the recommend KPI checks — gets
   `None` while the query still answers `200`. Six of the nine live
   `./do aito-check` cases fail this way on v2 with `KeyError: 'sku'`.
   Handling belongs in the compat layer (reconstruct v1's implicit default by
   injecting an explicit `select` derived from the link target's columns), and
   the silence is worth reporting upstream even though the capability exists.
