# ADR 0024: Precompute-and-serve store for heavy read endpoints

**Status:** Accepted
**Date:** 2026-07-22
**Deciders:** Antti

## Context

Six views are slow on a cold container: churn, demand, evaluation,
inventory, markdown, and winback. Measured live against the deployment
(`ecommerce.aito.ai`), cold:

| Page | Cold wall time | Dominant cost |
|------|---------------|---------------|
| churn | 32.7 s | one `_evaluate` = 15.5 s + per-customer `_predict` fan-out |
| demand | 32.9 s | one `_evaluate` = 16.1 s + 25× `_predict` |
| evaluation | 31.8 s | 4× `_evaluate` in parallel |
| inventory | 14.5 s | 25× `_predict` + aggregates |
| markdown | ~18 s | 75× `_estimate` |
| winback | fan-out per churned customer | `_recommend` + `_estimate` × N |

The other views (for-you, smart-search, bought-together,
purchase-analytics, filling, feedback, price, cart-completion) answer
in sub-second once warm and are **not** in scope — they are either
light or parameterised (per persona / query), so they can't reduce to a
single snapshot.

The **dashboard** is precomputed too, added after the initial six (see
Notes → "Dashboard is the seventh precomputed view"). It reads as
"light", but it's the landing view *and* it turned out to make ~321
sequential `_search` calls (~93 s cold) — the heaviest cold page of all
— so a cold-start visitor felt it first and worst.

Why the cold cost keeps biting in production specifically: the public
deploy runs with `PUBLIC_DEMO=1` against a **read-only** API key. Our
existing `src/cache.py` is a *lazy write-through* cache — it computes on
first hit and writes results to an in-memory layer plus an Aito
`prediction_cache` table (L2). Because L2 *writes*, it is disabled
entirely under `PUBLIC_DEMO` (`cache.py` `init_persistent_cache` is a
no-op). Consequences:

- Every container restart starts fully cold — nothing survives.
- The startup warmup (`src/cache_warmup.py`, a background daemon) must
  recompute all six heavy pages, and it walks them **last**.
- A visitor landing during that window pays the full 14–32 s cold cost
  of whatever heavy page they open.

None of this is an Aito regression, and the v2 engine does not fix it
(ADR 0023; the v2 `_evaluate` path is in fact ~2.5× slower and is a
separate promotion blocker). The heavy cost is inherent to running
`_evaluate` / large fan-outs at request time.

The fix is to **invert the write path**: run the heavy work *offline*
and have the running container only *read*. This is the pattern
`aito-accounting-demo/src/precompute_store.py` already uses; we adopt
it here for the six heavy endpoints.

## Aito usage

No new query *types*. The same `_evaluate` / `_predict` / `_estimate` /
`_relate` calls the six services make today, but run offline by
`./do precompute` and their JSON results stored in a new Aito table:

```json
// PUT /schema/precompute_entries
{
  "type": "table",
  "columns": {
    "name":        {"type": "String", "nullable": false},
    "payload":     {"type": "Text",   "nullable": false},
    "computed_at": {"type": "Int",    "nullable": false}
  }
}
```

Read path — one exact-match `_search` per key, which needs only a read
key:

```json
// POST /_search
{"from": "precompute_entries", "where": {"name": "churn"}, "limit": 1}
```

Writes (`/data/_delete` then `/data/precompute_entries`) happen only in
`./do precompute`, against a write key.

## Decision

Add `src/precompute_store.py`, mirroring accounting-demo: a read helper
with three layers — L1 in-process dict → Aito `precompute_entries` →
git-committed JSON at `data/precomputed/{name}.json` → `None`.

1. **`./do precompute`** computes the six heavy endpoints and `put()`s
   each result under its key (`churn`, `demand`, `evaluation`,
   `inventory`, `markdown`, `winback`). Run in CI/build before deploy.
2. **The six endpoints** read from the store first. On a store miss
   (local dev against a fresh Aito with no precompute table), they fall
   back to **live compute** so `./do dev` still works uncached.
3. **Six JSON bootstrap files** committed to `data/precomputed/` so a
   cold or unreachable Aito still serves the heavy pages instantly,
   and so the very first request after a fresh deploy needs no Aito
   round-trip at all.
4. **Preserve the latency pill.** Precomputed pages make no Aito call at
   read time, so the `X-Aito-Calls` header would vanish and the "look
   how fast the query is" teaching moment on exactly these pages would
   be lost. The precompute payload therefore records the per-call
   timings measured at compute time, and the endpoint re-emits them on
   the header — the pill shows the *real* query cost from an honest
   snapshot, not a fabricated number.

`src/cache.py` and the lazy warmup stay exactly as they are for the
light endpoints. This ADR adds a second, read-only mechanism alongside
it; it does not replace it.

## Acceptance criteria

- [ ] When the public container restarts cold, each of the six heavy
      pages returns in < 1 s (served from the precompute store, not
      recomputed).
- [ ] A user viewing a heavy page sees data identical to the
      live-computed version — the precompute is a faithful snapshot.
- [ ] `./do precompute` refreshes the store (Aito table) without a
      redeploy; a subsequent page load reflects the new values.
- [ ] With Aito unreachable, the six heavy pages still serve from the
      git-committed JSON bootstrap.
- [ ] With no snapshot in Aito, the six endpoints serve the committed
      JSON bootstrap; if that is absent too they fall back to live
      compute. Either way they return correct data (no error).
- [ ] The latency pill on a precomputed page shows the same per-query
      timings the live request would record — the load-bearing
      main-thread `_evaluate` / `_relate` / `_search` calls (see the
      thread caveat in Notes).

## Demo impact

All five demo moments preserved. The "predictive database is fast"
story is *strengthened* on the heavy pages — a live walkthrough no
longer risks a 32 s stall on churn/demand/evaluation. `docs/demo-script.md`
gains a note that heavy pages are served from a precompute snapshot and
that `./do precompute` refreshes it. The latency pill continues to show
honest per-query costs (criterion above), so the teaching value is
intact.

## Out of scope

- The remaining light / parameterised views (for-you, smart-search,
  bought-together, purchase-analytics, filling, feedback, price,
  cart-completion) — they stay on the lazy `cache.py`.
- Personalized / parameter-swept variants beyond each heavy endpoint's
  single canonical result (heavy pages take no user params today).
- Removing or refactoring `cache.py`.
- The v2 engine migration and its `_evaluate` slowdown (ADR 0023).

## Consequences

**Good:**
- Cold restart is instant for the six worst pages — the 14–32 s cliff
  is gone.
- Works with the read-only public key (reads, not writes).
- Refreshable without a redeploy (`./do precompute`).
- Git-committed JSON is a resilient bootstrap: no empty pages even if
  Aito is briefly unreachable, echoing the failure this pattern was
  designed around in accounting-demo.

**Bad:**
- Precomputed data is a snapshot — it goes stale between `./do precompute`
  runs. Acceptable here: the demo runs on static seed=42 fixtures that
  only change on an intentional data reload.
- Two cache mechanisms now live in the repo (lazy `cache.py` +
  read-served `precompute_store.py`). A reader must understand both;
  mitigated by clear module docstrings and this ADR drawing the line
  (heavy/offline vs light/lazy).
- The latency-pill snapshot adds a small amount of plumbing to each of
  the six services (record + stash timings at precompute time).

## Notes

- Mirrors `aito-accounting-demo/src/precompute_store.py`, including the
  git-drift failure story that motivated routing precompute through Aito
  rather than baking JSON into the image.
- Related: `src/cache.py` (lazy L1/L2 for light endpoints); ADR 0021
  (impressions KPI); ADR 0023 (v2 port — v2 `_evaluate` ~2.5× slower,
  tracked separately as a promotion blocker).
- Latency-pill thread caveat: the timing bucket is a `contextvar`,
  which does not propagate into `ThreadPoolExecutor` workers. So the
  pill only ever surfaced the calls a service makes on the request's
  own thread — true live *and* in the snapshot, so the two stay
  consistent. Concretely, churn/demand/inventory/markdown/winback
  capture their main-thread `_evaluate` / `_search` / `_relate` (the
  load-bearing costs); `evaluation`, whose four `_evaluate`s all run in
  workers, captures none — its pill was already effectively blank live.
  Surfacing worker-thread costs would mean propagating the context into
  every service's executor — a separate instrumentation change, tracked
  as a follow-up, deliberately out of scope here.
- Verified read path: a cold process serves `churn` from the store in
  ~116 ms (vs ~32 s recompute) with the pill showing the real
  `_evaluate:10974.6`.
- **Dashboard is the seventh precomputed view.** Added after the
  initial six because it's the *landing* page — the first thing every
  visitor loads, so its cold cost is felt before anything else.
  Precompute snapshotting also surfaced *why* it stalled: `get_dashboard`
  runs **~321 sequential `_search` calls** (~93 s cold), almost all from
  `_segment_cards`, which looped five segments × up to 60 customers
  doing one search per customer for the average-basket figure. So the
  "light" landing page was in fact the heaviest cold page in the demo.
  **That N+1 is now fixed** (same change set): the per-segment customer
  counts collapse into one `_batch`, and the average basket is one
  `_aggregate` on `customers` — `mean(total_spent_eur)/mean(total_orders)`,
  which reads `segment` natively (no `orders` join, ~20 ms vs ~2.9 s for
  the link-filtered form). `_recent_orders`' per-order line lookups were
  the same shape and got the same `_batch` treatment. Dashboard: **321
  Aito calls → 12**, and `./do precompute` for it dropped from ~93 s to
  ~10 s (the residual is `_compute_top_patterns`' six parallel `_relate`
  calls, inherent association-mining cost). New Aito patterns (`_batch`,
  aggregate-on-native-column) are documented in `docs/aito-cheatsheet.md`.
- Open question: should `./do precompute` run inside `./do reset-data`
  automatically (one command to reload + snapshot), or stay a separate
  step? Leaning toward chaining it into `reset-data` so the snapshot
  can never drift behind a data reload.
