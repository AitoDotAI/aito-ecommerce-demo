# ADR 0004: Layout shell + design tokens

**Status:** Accepted
**Date:** 2026-05-11
**Deciders:** Demo team

## Context

`TASK.md` reserves `predictive-ecommerce-demo.html` as the canonical
visual reference, then makes the rule explicit:

> Match `predictive-ecommerce-demo.html` exactly. … Match
> predictive-ecommerce-demo.html pixel-close before building any
> view content.

The framework doc (`aito-demo-framework.md §5`) locks the Aito side
panel — colours, typography, behaviour — as a cross-demo invariant.
Everything outside the panel (sidebar, topbar, content tokens) is
vertical-specific.

This ADR records:
1. The exact CSS class vocabulary lifted from the mock (not the
   ERP demo's `NavBar__` names).
2. The decision to ship Aito-panel structure from the mock too,
   because the mock already uses the canonical panel colours and
   layout — `#0c0f41` background, `#12B5AD` teal accents, `#9B69FF`
   purple section labels, monospace `aito..` wordmark.
3. The component split for React.
4. Responsive breakpoints.

## Decision

### CSS source-of-truth: the HTML mock, lifted verbatim

`predictive-ecommerce-demo.html` lines 7–476 contain the design
system in fully-realised form. The entire `<style>` block lands
in `frontend/app/globals.css` with minimal changes:

- Strip the demo-script-only `.view { display: none; } .view.active`
  bits; Next.js routes handle view switching.
- Keep every other rule — including the Aito-panel block — because
  the mock already follows the canonical panel palette.
- The CSS variables in `:root` are unchanged. The variable *names*
  (`--primary`, `--cta`, `--bg`, `--text`, `--aito-w`, `--font`)
  are this demo's tokens; the values match the zooplus-inspired
  palette `TASK.md` pinned.

### Class vocabulary (mock-style, not ERP-style)

| Element | Class | Notes |
|---|---|---|
| Top bar | `.topbar` + `.topbar-brand` + `.topbar-content` | Brand sits in the sidebar-width slot on desktop. |
| Sidebar | `.sidebar` + `.nav-section` + `.nav-item` | Active items get the warm-yellow left border `--cta`. |
| Main | `.main` (`.sidebar-collapsed`, `.aito-collapsed` modifiers) | Reads margin from sidebar/panel width vars. |
| Aito panel | `.aito-panel` + `.aito-panel-header` + `.aito-stats` + `.aito-panel-content` + `.aito-panel-cta` | Mock-style names; canonical colours. |
| Mobile overlay | `.pane-overlay` | Shared by sidebar + panel. Tap closes both. |

Sidebar sections, in order: **Overview · Assist Customers ·
Analyze · Automate**. Sidebar footer carries the always-on
`aito.ai · Predictive DB · 14,820 orders · 16ms avg` indicator
strip.

### Component split

```
frontend/components/shell/
  AppShell.tsx       # wraps every page: TopBar + Sidebar + Aito panel + main slot
  TopBar.tsx         # brand + breadcrumb + actions (Export, Live Demo, panel toggle, avatar)
  Sidebar.tsx        # nav sections + items + sidebar footer
  AitoPanel.tsx      # right-rail panel, reads AitoPanelConfig (lib/types.ts)
  LatencyBadge.tsx   # ported verbatim from aito-erp-demo
  ErrorState.tsx     # ported verbatim from aito-erp-demo
  ShellState.tsx     # client component holding collapse/mobile state
```

`AppShell` is a Client Component (uses `useState` for collapse
state). Pages remain Server Components by default and get the
shell from `app/layout.tsx`.

```
frontend/components/prediction/
  PredictionBadge.tsx
  ConfidenceBar.tsx
  WhyTooltip.tsx
  PredictedField.tsx
  LiftHint.tsx       # new — inline "× 3.1" annotation, green/grey/red by lift band
```

### Responsive breakpoints

Single breakpoint at **`max-width: 900px`** — matches the mock's
JavaScript `isMobile = () => window.innerWidth <= 900`.

| Width | Sidebar | Aito panel |
|---|---|---|
| > 900px | always-open, collapsible (chevron in `.topbar-brand`) | always-open, collapsible (lightning toggle in topbar actions) |
| ≤ 900px | off-canvas drawer (hamburger toggle on left), `.pane-overlay` backdrop | off-canvas drawer (panel toggle on right), shared overlay |

Two-panes-open-at-once is disallowed by JS — opening one closes
the other. Matches the mock.

### Per-view content

Each view in `TASK.md` gets:
- `frontend/app/<route>/page.tsx` — Server Component, fetches its
  data + sets its `AitoPanelConfig` for the panel.
- A builder in `frontend/lib/panel-content.ts` keyed by route.

This ADR ships **empty page scaffolds** for all eight views (so
nav links resolve) and **panel-content stubs** that carry the
right endpoint badges + a one-line description. The data fetch +
real content lands in each view's own ADR.

## Acceptance criteria

- [ ] `./do dev` renders the shell on every route at
      `http://localhost:8500`.
- [ ] Sidebar collapse + Aito-panel collapse work on desktop
      (chevron + lightning toggle).
- [ ] Mobile breakpoint (`< 900 px`) hides both side rails and
      surfaces them as overlay drawers.
- [ ] Routes resolve for: `/`, `/smart-search`, `/recommendations`,
      `/bought-together`, `/purchase-analytics`,
      `/pattern-explorer`, `/product-filling`, `/evaluation`.
- [ ] No regression in existing tests (20/20 green).

## Demo impact

Sets the visual stage for every later view. Each demo moment —
Smart Search rank flip, For You grid switch, Bought Together
lift, Product Filling fields, Evaluation row colours — depends on
the shell being correctly framed so the panel + topbar context
read consistently.

## Out of scope

- View content (Dashboard's KPIs, Smart Search's results, etc.) —
  per-view ADRs from 0005 onwards.
- Live wiring of `AitoPanel` to each page's actual last query —
  the field exists in `AitoPanelConfig` from the scaffold; pages
  will populate it when their `_predict` / `_relate` /
  `_recommend` calls land.

## Consequences

**Good:**
- Lifting the mock's CSS verbatim is the fastest path to
  pixel-fidelity. A reviewer comparing the running app against
  the mock has nothing to argue with.
- Mock-style class names (`.nav-item` not `.NavBar__menuItem`)
  read straight from the HTML source. An outside developer can
  ⌘-click between `.nav-item` in `globals.css` and `<div
  class="nav-item">` in `Sidebar.tsx`.

**Bad:**
- Class-name divergence from `aito-erp-demo`'s `NavBar__*` /
  `topbar-*` mix is a cross-demo inconsistency. The framework
  doc says "the token *names* in `globals.css` stay the same"
  but the *element* class names are vertical-specific — this is
  consistent with that rule. Future ADRs in other demos may
  converge if a third vertical also lifts from a mock.
- The mock's CSS is bigger than strictly necessary (it carries
  styles for view content not yet built). We carry them anyway;
  pruning later as views land is cleaner than discovering missing
  styles mid-build.

## Notes

- The mock uses inline styles in many places (e.g. `style="display:flex"`
  in the segment cards). The React components extract those into
  scoped classes (`.dashboard-segment-row`) so the JSX stays
  readable. Inline styles in the *mock* are a side-effect of
  it being a single-file artefact; React doesn't have that
  constraint.
- The mock's `views` JavaScript object (lines 1572–1613) is the
  draft for `lib/panel-content.ts`. The descriptions and example
  queries are the right starting point but must be replaced with
  *real* runnable queries before each view's ADR is accepted
  (CLAUDE.md prime directive #3).
