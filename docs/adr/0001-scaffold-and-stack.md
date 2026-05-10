# ADR 0001: Scaffold + stack mirrored from `aito-erp-demo`

**Status:** Accepted
**Date:** 2026-05-10
**Deciders:** Demo team

## Context

`aito-ecommerce-demo` is the third public Aito vertical demo, after
`accounting.aito.ai` and `erp.aito.ai`. The cross-demo framework
document (`aito-demo-framework.md`) and `TASK.md` both prescribe the
shape of every new demo: Python FastAPI + Next.js 16, two-layer cache,
locked Aito side panel, port pair per demo, single-file `app.py`,
one service module per view.

The decisions below are deliberate restatements of the framework so
that the choices are visible to a developer reading this repo cold —
without making them re-derive from the framework doc.

## Aito usage

The scaffold itself uses only `_GET /schema` (via
`AitoClient.check_connectivity()`) so `/api/health` can report whether
the configured `AITO_API_URL` / `AITO_API_KEY` resolves. Real query
patterns (`_predict`, `_relate`, `_recommend`, `_search`, `_match`,
`_evaluate`) land in subsequent ADRs paired with their views.

## Decision

1. **Stack.** Python 3.12 + FastAPI on port `8501`, Next.js 16
   (App Router) on port `8500`. No alternative ports — the framework
   doc reserves `8500/8501` for ecommerce.
2. **Single tenant.** PetNord is the one and only persona; the
   multi-tenant routing in `aito-erp-demo` is dropped. `src/config.py`,
   `src/cache.py`, `src/aito_client.py`, `frontend/lib/api.ts` all
   ship without the per-tenant code paths.
3. **Mirror, don't reinvent.** The `AitoClient`, `cache.py`,
   `rate_limit.py`, `timing.py`, the AitoPanel React component, and
   the prediction primitives (`PredictionBadge`, `ConfidenceBar`,
   `WhyTooltip`, `PredictedField`, `LiftHint`) are copied verbatim
   from `aito-erp-demo` and trimmed for single tenant — these are
   cross-demo invariants per the framework doc.
4. **Visual language.** Application chrome uses the zooplus-inspired
   palette pinned in `predictive-ecommerce-demo.html`: dark forest
   green `#1B4332` sidebar, `#F5F7F5` page background, `#F5A623`
   warm-yellow CTA, Nunito for prose, JetBrains Mono for code. The
   Aito side panel keeps its locked colours (`#0c0f41` indigo,
   `#12B5AD` teal, `#9B69FF` purple) — the panel is the brand.
5. **`./do` script.** Same verbs as the other demos (`dev`,
   `backend-dev`, `frontend-dev`, `load-data`, `reset-data`,
   `clear-cache`, `test`, `aito-check`, `verify`, `verify-demo`,
   `check`, `demo`, `fmt`, `setup`, `generate-fixtures`). Cross-demo
   muscle memory beats novelty.

## Acceptance criteria

- [ ] `./do dev` boots both servers; `http://localhost:8500` renders
      a placeholder page; `http://localhost:8501/api/health` returns
      `{ "ok": true, "aito_connected": <bool> }`.
- [ ] `.env.example` documents `AITO_API_URL`, `AITO_API_KEY`, and
      the public-demo flags (`PUBLIC_DEMO`, `CORS_ORIGINS`,
      `RATE_LIMIT_*`).
- [ ] No code in `src/` references multi-tenant concepts (`tenant`,
      `X-Tenant`, per-tenant API URL pairs).

## Demo impact

This is the foundation for every later view; on its own it ships no
demo moments. The "five demo moments" in `TASK.md` (Smart Search,
For You, Bought Together, Product Filling, Evaluation) all build on
top of this scaffold.

## Out of scope

- Fixtures, data loader, schema upload — ADR 0002.
- Layout shell (TopBar / Nav / AitoPanel rendering, design tokens) —
  ADR 0004.
- Any of the eight views — ADRs 0005 onward.

## Consequences

**Good:**
- Picks up every cross-demo affordance for free: latency badge,
  X-Aito-Calls header, two-layer cache, public-demo lockdown, the
  exact AitoPanel a CTO already trusts from the other two demos.
- Reading this repo after the other two reads as "of course" — same
  shape, different vertical.

**Bad:**
- Carrying ERP-demo code without its callers means we have to be
  vigilant about dead code as views land. We delete unused branches
  in the same PR they become unused; nothing sits "ready for the
  next view" without being wired.
- The framework doc and three demos now have to stay in lockstep on
  the cross-demo invariants. Any change to the AitoPanel, the cache
  shape, or the `do` verbs is an ADR + framework-doc update, not a
  one-off edit.

## Notes

- TASK.md build order: scaffold (this ADR) → fixtures → client &
  cache wiring → layout shell → Dashboard → Smart Search → For You
  → Bought Together → Purchase Analytics → Pattern Explorer →
  Product Filling → Evaluation → live Aito mode.
- This ADR explicitly does *not* re-decide the cross-demo invariants
  (panel colours, prediction primitives, port allocation, public-demo
  flag set). To change any of those, open an ADR that supersedes the
  framework doc, not this one.
