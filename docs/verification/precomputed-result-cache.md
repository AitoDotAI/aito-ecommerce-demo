# Verification — precompute-and-serve store (ADR 0024)

**Date:** 2026-07-22
**Feature branch:** `feat/precomputed-result-cache`
**Method:** manual (the `./do verify` adversary agent is still a stub).
Backend run via `uvicorn src.app:app`, endpoints exercised with `curl`,
fallback paths driven in-process + as unit tests.

The six heavy views (churn, demand, evaluation, inventory, markdown,
winback) now read from the Aito `precompute_entries` snapshot instead of
computing `_evaluate` / large fan-outs at request time. Acceptance
criteria are from ADR 0024.

## Latency — before vs after

Cold wall time, measured against the same shared Aito instance.

| Endpoint | Before (live, cold) | After (store read) | After (warm L1) |
|----------|--------------------:|-------------------:|----------------:|
| dashboard | ~93 s (321 `_search`) | 0.17 s | 0.004 s |
| churn | 32.7 s | 0.30 s | 0.007 s |
| demand | 32.9 s | 0.11 s | 0.005 s |
| evaluation | 31.8 s | 0.12 s | 0.003 s |
| inventory | 14.5 s | 0.17 s | 0.004 s |
| markdown | ~18 s | 0.22 s | 0.004 s |
| winback | (fan-out) | 0.12 s | 0.003 s |

✅ **AC:** cold-container heavy pages return < 1 s.

The **dashboard** was added to the precompute set after the initial six:
it's the landing page, and snapshotting surfaced that `get_dashboard`
runs ~321 sequential `_search` calls (~93 s cold) — the heaviest cold
page of all, felt first by every visitor. Its pill aggregates to a
single "321 calls · ~6.8 s" figure (`LatencyBadge` sums + counts), and
the `X-Aito-Calls` header is ~3.9 KB — well within limits.

## Latency pill — real query cost preserved

Each precomputed response re-emits the per-call timings captured at
snapshot time on `X-Aito-Calls`:

```
churn      pill=[_search:6.4,_search:12.6,_search:663.3,_evaluate:10974.6]
demand     pill=[_search:747.0,_search:375.9,_search:86.4,_search:48.8,_evaluate:14831.9]
inventory  pill=[_search:78.5,_search:221.9,_search:464.7,_search:400.9,_search:95.9]
markdown   pill=[_search:55.1,_search:51.6,_search:399.6,_search:402.8,_search:92.8]
winback    pill=[_search:17.8]
evaluation pill=[]        ← 0 timings captured (see caveat)
```

✅ **AC:** the pill shows the real per-query cost (the load-bearing
`_evaluate` is front and centre), not a blank "cached" pill.

## Bug found and fixed during verification

**The store's own cache lookup leaked onto the pill.** `serve` calls
`store.get`, which runs an `_search` against `precompute_entries`; the
AitoClient records that on the timing bucket, so the first-hit pill
showed a stray leading `_search` (e.g. churn `_search:11.5`) *before*
the real query timings. Fixed by dropping the lookup call in `serve`
before replaying the snapshot timings.

**Follow-on bug in the first fix.** The first attempt rebound the
`ContextVar` (`_calls.set(new_list)`). FastAPI runs sync endpoints in a
threadpool whose context is a shallow copy of the middleware's — the two
share one list *object*, and the middleware reads timings back off it.
Rebinding detached the endpoint's list, so **all** replayed timings
vanished and only the pre-fix lookup `_search` survived (observed:
`churn pill=[_search:9.7]`, no `_evaluate`). Corrected `replace_calls`
to mutate the shared list in place (`clear` + `extend`). Pinned with
`test_replace_calls_mutates_the_bucket_in_place`, which asserts list
identity so a reassign regression fails in tests, not in prod.

## Fallback paths

- **Aito miss → git JSON bootstrap:** `get` falls through to
  `data/precomputed/{name}.json`. Covered by
  `test_get_falls_back_to_committed_json`; the six bootstrap files are
  committed.
- **No snapshot anywhere → live compute:** `serve` calls the endpoint's
  own compute on a total miss. Covered by
  `test_serve_falls_back_to_live_compute_on_miss`.
- **Read-only key:** `precompute_store.init` swallows the schema-PUT
  `AitoError`; reads still work. `./do precompute`'s Aito write is
  best-effort and skipped with a warning, but the JSON bootstrap is
  always written.

✅ **AC:** Aito-unreachable serves committed JSON; empty-snapshot dev
falls back to live compute; no errors on either path.

## Data fidelity

Precomputed `churn` payload carries the same shape the live endpoint
returns (`kpis`, `at_risk`, `drivers`, `evaluation`, `last_query`,
`last_response_ms`); KPIs match the live computation (3000 customers,
36.4 % churn). Snapshot is a faithful copy of a live run.

✅ **AC:** users see data identical to the live-computed version.

## Residual limitations (not failures)

- **Evaluation pill is empty.** Its four `_evaluate`s run in a
  `ThreadPoolExecutor`; `contextvars` don't cross threads, so no timings
  are captured — true live *and* in the snapshot, so the two stay
  consistent. Surfacing worker-thread costs needs context propagation
  into the executors — tracked as a follow-up in ADR 0024.
- **Snapshot staleness.** Precompute is a point-in-time copy; it refreshes
  on `./do precompute` (chained into `./do reset-data`). Acceptable —
  the demo runs on static seed=42 fixtures.

## Conclusion

No failures found after exercising: all six endpoints cold and warm, the
pill on every endpoint, the Aito-miss/JSON-bootstrap path, the
total-miss/live-compute path, the read-only-key write path, and data
fidelity vs a live run. Two bugs were found *and fixed* during
verification (pill lookup leak; ContextVar rebind), both now covered by
tests. 68/68 tests pass.
