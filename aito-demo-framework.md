# Aito Demo Framework — Reference

Conventions, shared components, and re-usable patterns across the Aito
vertical demos:

- **`aito-demo`** — the original grocery-store reference application
  (`https://github.com/AitoDotAI/aito-demo`). The `ContextPanel` design
  there is the canonical Aito-panel reference; later demos import its
  visual language.
- **`aito-accounting-demo`** — first OSS vertical demo, live at
  `accounting.aito.ai`. The reference implementation for everything in
  this document.
- **`aito-erp-demo`** — second OSS vertical demo, live at
  `erp.aito.ai`. Multi-persona variant; shares all infrastructure
  with accounting-demo.
- **`aito-ecommerce-demo`** — third vertical demo, in progress.
  Should follow this document end-to-end.

When this document and a specific demo's `CLAUDE.md` disagree, the
demo's `CLAUDE.md` wins for that project, and this document should be
updated to reflect the new convention.

---

## 1 — What's shared, what varies

| Layer | Shared across demos | Vertical-specific |
|---|---|---|
| Stack | Python 3.12 / FastAPI, Next.js 16 / TypeScript, Aito free tier | — |
| Project skeleton | `src/` `frontend/` `data/` `tests/` `docs/` `do` `shell.nix` | — |
| Aito client | `aito_client.py`, two-layer cache, error shape | — |
| FastAPI `app.py` | endpoint shape, error envelope, `/api/schema` route | per-service routes |
| Data loader | `data_loader.py` reads JSON fixtures, uploads schema | the schema and JSON shape |
| Rate limiting | `rate_limit.py`, three-tier envelope | tier limits if needed |
| Frontend shell | `TopBar`, `Nav`, `AitoPanel`, `ErrorState`, mobile-overlay behaviour | brand mark, sidebar items |
| Prediction primitives | `PredictionBadge`, `ConfidenceBar`, `WhyTooltip`, `PredictedField` | — |
| Aito panel JSON shape | `AitoPanelConfig` contract, lifecycle | per-view content |
| Design tokens (panel) | deep indigo `#0c0f41`, teal `#12B5AD`, purple `#9B69FF` | — |
| Design tokens (chrome) | nav bg, main bg, card bg, accent, fonts | actual palette + accent |
| `do` script | command names (`dev`, `setup`, `load-data`, `test`, `check`) | port numbers |
| Public-demo flags | `PUBLIC_DEMO=1`, CORS lockdown, schema 404, mem-only cache | tier limits |
| Analytics | Amplitude event names + GA setup, latency badge | — |
| Testing | `booktest` for review-driven regression on Aito output | per-service tests |

The rule: **if it touches Aito or the demo's credibility (the panel, the
prediction components, the error shape), it's shared. If it's about the
domain (data, copy, palette accent), it's vertical.**

---

## 2 — Project skeleton

Every demo has the same top-level layout:

```
.
├── CLAUDE.md                          # OSS reference + project specifics
├── TASK.md                            # (new demos) executable build brief
├── README.md                          # Three-audience README
├── pyproject.toml                     # uv-managed Python deps
├── .env / .env.example                # AITO_API_URL, AITO_API_KEY, PUBLIC_DEMO, …
├── shell.nix                          # Nix dev environment
├── do                                 # Task runner
│
├── src/                               # Python FastAPI backend
│   ├── app.py                         # All endpoints; FastAPI main
│   ├── config.py                      # Env loading
│   ├── aito_client.py                 # Thin Aito REST wrapper
│   ├── cache.py                       # Two-layer cache
│   ├── rate_limit.py                  # IP-based rate limiting
│   ├── data_loader.py                 # Schema + fixture upload
│   └── *_service.py                   # One service per view
│
├── frontend/                          # Next.js 16 (App Router)
│   ├── app/
│   │   ├── layout.tsx                 # Root layout + Google Fonts
│   │   ├── globals.css                # Full design system
│   │   └── <view>/page.tsx            # One page per view
│   ├── components/
│   │   ├── shell/                     # TopBar, Nav, AitoPanel, ErrorState, …
│   │   └── prediction/                # PredictionBadge, ConfidenceBar, …
│   └── lib/
│       ├── api.ts                     # apiFetch, fmt helpers
│       ├── analytics.ts               # Amplitude + GA wrapper
│       ├── types.ts                   # AitoPanelConfig, …
│       └── panel-content.ts           # Per-view Aito-panel payloads
│
├── data/                              # JSON fixtures
│   ├── generate_fixtures.py
│   └── *.json
│
├── tests/                             # pytest + booktest
└── docs/
    ├── adr/                           # Architecture Decision Records
    ├── aito-cheatsheet.md             # Verified Aito query patterns
    ├── data-model.md                  # Schema explanation
    ├── demo-script.md                 # 2-minute live walkthrough
    └── use-cases/                     # (erp-demo style) per-feature deep-dives
```

### Port allocation

Each demo runs on its own port pair so they can run side-by-side
locally:

| Demo | Frontend | Backend |
|---|---|---|
| `aito-accounting-demo` | 8300 | 8301 |
| `aito-erp-demo` | 8400 | 8401 |
| `aito-ecommerce-demo` | 8500 | 8501 |

Always two ports — Next.js proxies the API. New demos take the next
free pair.

---

## 3 — Backend patterns

### 3.1 `aito_client.py` — thin REST wrapper

The client is intentionally small. It does one thing: make an HTTP
call to a single Aito endpoint with retries and a clear error shape.
Service modules build query bodies and call the client; the client
does not know about views, services, or business logic.

Shape (cross-demo invariant):

```python
class AitoError(Exception):
    """Raised when Aito returns a non-2xx response or invalid JSON.

    Attributes:
        status_code: HTTP status from Aito (or 0 for transport errors)
        endpoint:    Aito endpoint called (e.g. "_predict")
        body:        Parsed JSON error body if available, else raw text
    """

class AitoClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 10.0): ...
    def predict(self, table: str, where: dict, predict: str, **opts) -> dict: ...
    def recommend(self, table: str, goal: dict, **opts) -> dict: ...
    def relate(self, table: str, where: dict, relate: str, **opts) -> dict: ...
    def search(self, table: str, where: dict, **opts) -> dict: ...
    def evaluate(self, table: str, predict: str, test: dict, **opts) -> dict: ...
    def schema(self) -> dict: ...
    def upload_schema(self, schema: dict) -> None: ...
    def upload_rows(self, table: str, rows: list[dict]) -> None: ...
```

Conventions:

- Methods take a positional `table` first, keyword arguments for the
  rest. Mirrors the JSON body shape and reads naturally at the call
  site.
- `**opts` carries through `select`, `limit`, `orderBy` etc. without
  the wrapper having to enumerate them.
- All methods raise `AitoError` on failure. **Never** swallow errors
  or return empty dicts on failure — surface them.
- The client never logs PII. It logs endpoint, latency, and status code.

### 3.2 Service modules — one per view

Each view has a service file (`invoice_service.py`,
`recommend_service.py`, …). The service module is responsible for:

1. Building the Aito query body
2. Calling `AitoClient`
3. Translating the response to the API DTO the frontend expects
4. Adding the `last_query` and `last_response_ms` fields the Aito
   panel uses to display the actual query that ran

Example shape (illustrative, reproduce the patterns from
`aito-accounting-demo/src/invoice_service.py`):

```python
def predict_invoice_account(
    client: AitoClient,
    invoice: Invoice,
    cache: Cache,
) -> InvoicePrediction:
    # 1. Build the query body
    where = {"vendor": invoice.vendor, "description": invoice.description}
    body = {
        "from": "invoices",
        "where": where,
        "predict": "account_code",
        "select": ["$p", "feature", {"$why": {}}],
    }

    # 2. Cache lookup keyed on (table, where, predict)
    cached = cache.get("predict", body)
    if cached is not None:
        return _to_dto(cached, body, ms=0)

    # 3. Call Aito and time it
    started = time.monotonic()
    response = client.predict(**body)
    ms = int((time.monotonic() - started) * 1000)

    # 4. Cache and return
    cache.put("predict", body, response)
    return _to_dto(response, body, ms=ms)
```

The `last_query`/`last_response_ms` fields end up in the JSON the
frontend page returns alongside its data — the `AitoPanel` component
reads them and displays the actual query body that ran (see §5.3).

### 3.3 `cache.py` — two-layer cache

Predictions are deterministic for a given `where`+`predict`, so we
cache them. Two layers:

1. **In-memory LRU** for the current process (fast).
2. **Aito-backed table** (`prediction_cache`) for warm-cache survival
   across restarts. Only used when `PUBLIC_DEMO=0`; in public mode the
   cache is memory-only because the public demo runs with a read-only
   Aito API key.

Cache keys are the SHA-256 of the canonicalised query body. Never key
on user-supplied IDs directly — the body covers it.

### 3.4 `rate_limit.py` — three-tier IP-based envelope

Active when `PUBLIC_DEMO=1`. Three tiers:

```
RATE_LIMIT_PER_IP       (e.g. 60/min)   — protects from a single bad actor
RATE_LIMIT_PER_TENANT   (e.g. 600/min)  — guards multi-persona demos
RATE_LIMIT_GLOBAL       (e.g. 3000/min) — total ceiling
```

Localhost bypasses the per-IP tier so screenshot-generation and
booktest tooling still runs at full speed.

### 3.5 `app.py` — FastAPI shape

Conventions:

- **One file** for all routes, no router fragmentation. Demos are small
  enough that `app.py` is the table of contents.
- **DTOs are dataclasses** with `to_dict()` methods. No Pydantic.
- **Error envelope** for all endpoints: `{"error": {"code": "...",
  "message": "..."}, "status": 4xx}`.
- `/api/schema` returns the live Aito schema in dev mode, **404 in
  public-demo mode** (don't leak the table layout).
- `/api/health` is unauthenticated and returns `{"ok": true}`.
- All other `/api/*` routes pass through the rate limiter.

---

## 4 — The `do` script

Common workflows are encoded as `./do <verb>` to avoid permission
friction and so that Claude Code can run them autonomously without
confirmation prompts on every command.

Verbs that **every demo must implement** (so cross-demo muscle memory
holds):

```
./do help              # List all commands
./do setup             # uv sync + npm install
./do dev               # Start backend and frontend together
./do backend-dev       # Start FastAPI only (port = backend port)
./do frontend-dev      # Start Next.js only (proxies to backend)
./do frontend-build    # Build static export
./do load-data         # Upload schema + fixtures to Aito
./do reset-data        # Drop and reload all Aito tables
./do clear-cache       # Clear prediction cache
./do test              # Run pytest + booktests
./do aito-check        # Sanity-check Aito queries against fixtures
./do verify <feature>  # Run adversary Playwright agent for one feature
./do verify-demo       # End-to-end demo-path check
./do check             # Pre-merge gate (test + fmt + aito-check)
./do demo              # Run demo from a clean state
./do fmt               # Format code
```

Verbs that are demo-specific (only add when the demo needs them):

```
./do generate-fixtures   # Re-run the deterministic fixture generator
./do generate-personas   # (erp-demo) build the per-persona JSON splits
./do azure-deploy        # (accounting-demo) Azure Container Apps deploy
./do precompute          # (accounting-demo) populate precomputed mode
```

**Rule:** if you run the same multi-step command twice, add it to `do`
in the same PR.

---

## 5 — Frontend shell

Reference implementation: `aito-accounting-demo/frontend/components/shell/`.

### 5.1 `TopBar.tsx`

Layout: brand-mark + store-name on the left (sits above the sidebar
width), centred breadcrumb, action buttons on the right (Export, Live
Demo, Aito-panel toggle, avatar). The brand-mark reuses the `--accent`
token; the breadcrumb uses `--text-muted` for parents and `--text` for
the current page.

Navigation toggle for mobile lives here, not on the sidebar — keeps
the sidebar pure.

### 5.2 `Nav.tsx` — sidebar

Sections labelled with small uppercase tracking text (`Overview`,
`Assist Customers`, `Analyse`, `Automate` for ecommerce; `Procurement`,
`Intelligence`, `Product`, `Operations`, `Overview` for ERP; etc.).
Items are flat under each section, with optional badges (`Live`,
`98%`, `New`).

Footer of the sidebar carries the always-on `aito.ai` indicator strip:

```
● aito.ai · Predictive DB
  14,820 orders · 16ms avg
```

This is a quiet reminder of who's powering the predictions, even when
the right panel is collapsed.

### 5.3 `AitoPanel.tsx` — the canonical sales-engineer panel

This is the single most important component to keep consistent across
demos. It does sales-engineer work during a live demo: explains what
the page is doing, names the Aito endpoint(s), shows the actual query
that ran, and routes the viewer to docs and the free trial.

**Visual identity (locked):**
- Background: `#0c0f41` (deep indigo)
- Stats values + CTA: `#12B5AD` (teal)
- Section labels + endpoint badges: `#9B69FF` (purple)
- Body text: rgba off-white
- Logo: monospace `aito..` wordmark with teal `em` on the `ai`
- Code block: `rgba(255,255,255,0.07)` translucent on dark, purple-tinted border

**Behaviour:**
- Collapsible on desktop (chevron toggle), persisted in
  `localStorage["aitoPanelCollapsed"]`.
- Bottom-sheet on mobile: a floating action button with the Aito logo
  opens it; an overlay closes it. Mobile state is independent of
  desktop collapsed state so the two breakpoints don't fight on
  resize.
- Header / stats / CTA stay pinned. Only the middle is scrollable —
  the "Start free trial" button is always reachable.

**Contract — `AitoPanelConfig`** (in `frontend/lib/types.ts`):

```ts
export interface AitoPanelStat {
  /** Numeric value as string. Special tokens "$invoices", "$employees"
   *  are resolved at render time from CustomerContext. */
  value: string;
  label: string;
}

export interface AitoPanelLink {
  label: string;
  url: string;
}

export interface AitoFlowStep {
  n: number;
  produces: string;        // human-readable, e.g. "Top 5 candidate accounts"
  call: string;            // e.g. "_predict on invoices, predict=account_code"
}

export interface AitoPanelConfig {
  operation: string;       // single endpoint badge, e.g. "_predict"
  description: string;     // HTML-allowed; the why-of-this-page sentence
  stats: AitoPanelStat[];  // 3-4 small KPIs at the top
  query: string;           // example query, JSON-stringified for the code block
  links: AitoPanelLink[];  // "Learn more" — docs, GitHub, etc.
  flow_steps?: AitoFlowStep[]; // optional, only shown during a guided tour
}
```

**Lifecycle.** Each `app/<view>/page.tsx` does three things:

1. Imports its `AitoPanelConfig` from `lib/panel-content.ts`.
2. Tracks the *actual* last query and latency it just ran.
3. Renders `<AitoPanel config={config} lastQuery={...} lastResponseMs={...} />`.

When `lastQuery` is set, the panel shows it (and the response time);
when not, it falls back to `config.query`. **Every query in
`config.query` must be runnable against the demo data.** No
aspirational queries.

**Per-view content.** `frontend/lib/panel-content.ts` exports one
config per view:

```ts
import type { AitoPanelConfig } from "./types";

export const dashboardPanel: AitoPanelConfig = {
  operation: "_relate",
  description:
    "Pattern discovery across all order data. Lift scores for product " +
    "co-occurrences and customer segments come from a single " +
    "<code>_relate</code> query.",
  stats: [
    { value: "$orders",   label: "Orders" },
    { value: "16ms",      label: "Avg latency" },
    { value: "0",         label: "Models trained" },
    { value: "EU",        label: "Hosting" },
  ],
  query: JSON.stringify({
    from: "orders",
    where: { product_category: "dry-food" },
    relate: "purchases",
    select: ["lift", "related"],
  }, null, 2),
  links: [
    { label: "View live schema",     url: "/api/schema" },
    { label: "Query API reference",  url: "https://aito.ai/docs/api/" },
    { label: "Source on GitHub",     url: "https://github.com/AitoDotAI/aito-ecommerce-demo" },
  ],
};
```

**The trick the panel does — embedded customer ID swap.** The example
queries embed a placeholder customer ID like `"CUST-0000"` so the JSON
on screen looks copy-paste-ready. When a different customer is
selected (in demos that have a customer switcher), the panel swaps
the literal at render time:

```tsx
const exampleQuery = customerId && customerId !== "CUST-0000"
  ? config.query.replaceAll('"CUST-0000"', `"${customerId}"`)
  : config.query;
```

This is small but it sells the demo: viewers see the panel "react" to
their interactions.

### 5.4 `ErrorState.tsx`

Single error component, used everywhere a fetch can fail. Variants:
`compact` (inline in a card) and `page` (full view fallback). Always
shows the actual error message — never "something went wrong". Errors
during a live demo are recoverable; silent failures are not.

### 5.5 Mobile / responsive behaviour

Three breakpoints, consistent across demos:

| Width | Sidebar | Aito panel |
|---|---|---|
| ≥ 1280px | always open | always open, collapsible |
| 768–1279px | toggle (overlay) | toggle (overlay) |
| < 768px | toggle (full-screen drawer) | bottom-sheet, FAB-triggered |

A single overlay element (`.pane-overlay`) closes either side panel
when tapped; it appears only when at least one panel is open on a
narrow viewport.

---

## 6 — Prediction primitives

Reference: `aito-accounting-demo/frontend/components/prediction/`. These
five components carry the Aito-specific UI vocabulary across all
demos. **Reuse, don't reimplement.**

### 6.1 `PredictionBadge`

Renders a single predicted value with confidence chip. Three confidence
tiers, picked by `confClass(p)` in `lib/api.ts`:

| Tier | Range | Visual |
|---|---|---|
| high | p ≥ 0.80 | green chip, value bold |
| medium | 0.50 ≤ p < 0.80 | gold chip, value normal |
| low | p < 0.50 | red chip, pulsing `!` warning |

```tsx
<PredictionBadge value="Production" confidence={0.91} />
```

### 6.2 `ConfidenceBar`

Horizontal bar showing the predicted-value probability against the
next-best alternative. Used in tabular contexts (PO Queue,
Recommendations).

### 6.3 `WhyTooltip`

Reads Aito's `$why` decomposition and renders it as a popover:
- Base rate
- Top contributing patterns with their lift multipliers
- Multiplicative chain ending in the final probability
- Top alternatives

The popover is the demo's auditability story — every prediction is
explainable. **Never** simplify or summarise the chain; show the
arithmetic verbatim.

### 6.4 `PredictedField`

A form-field element with three visual states:

- **Empty** — neutral border, placeholder
- **Predicted** — gold tint, value filled in by Aito, ⓘ icon for
  WhyTooltip, Tab to accept / Esc to reject
- **User** — neutral border, value typed/picked by user

When user-edited, the override becomes training data for the next
prediction (in the demo's narrative; in practice the new row gets
added to Aito on form submit).

### 6.5 `LiftHint`

Inline "× 3.1" lift annotation, colour-coded:

| Lift | Colour |
|---|---|
| ≥ 1.5× | green (positive) |
| 0.7–1.5× | grey (neutral) |
| < 0.7× | red (protective / negative) |

Used in `_relate` results tables (Pattern Explorer, Bought Together,
Supplier Intel).

---

## 7 — Analytics

Two systems wired in parallel:

- **Amplitude** — in-product behaviour, named events for every Aito
  endpoint call. Lets us see *which views are demo-loadbearing* across
  outreach.
- **Google Analytics** — acquisition attribution, page views, source
  tracking from outreach.

Wrapper: `frontend/lib/analytics.ts`. Conventions:

- Event names are snake_case verbs: `predict_account`, `recommend_for_you`,
  `evaluate_run`. The verb mirrors the service module.
- Properties always include `view`, `latency_ms`, `endpoint`.
- The `LatencyBadge` / `LatencyTicker` components in the shell read
  the same data — you see latency live during a demo, and it's logged.

---

## 8 — Design system

### 8.1 Aito panel — locked across all demos

(see §5.3 above) — `#0c0f41` / `#12B5AD` / `#9B69FF`, monospace
`aito..` wordmark, JetBrains Mono / IBM Plex Mono for code. **Do not
recolour the panel per vertical. The panel is the brand.**

### 8.2 Application chrome — vertical-specific

Each demo picks its own palette for nav, content, and accents — but
the shape of the token system is shared. The token names below must
exist in every demo's `globals.css`:

```css
:root {
  /* nav and chrome */
  --nav-bg:        ...;   /* sidebar background */
  --nav-text:      ...;   /* sidebar text */
  --nav-active:    ...;   /* active item background */

  /* content */
  --bg:            ...;   /* page background */
  --card-bg:       #ffffff;
  --border:        ...;
  --border-light:  ...;

  /* text */
  --text:          ...;   /* primary */
  --text-2:        ...;   /* secondary */
  --text-muted:    ...;   /* tertiary, captions */

  /* accent — the vertical's signature colour */
  --accent:        ...;
  --accent-bg:     ...;
  --accent-border: ...;

  /* semantic — same across demos */
  --green:  #16a34a;
  --red:    #dc2626;
  --amber:  #d4a030;
  --blue:   #1B5E9E;
  --purple: #6B3FA0;

  /* Aito panel — LOCKED, do not change per demo */
  --aito-bg:       #0c0f41;
  --aito-teal:     #12B5AD;
  --aito-purple:   #9B69FF;
  --aito-border:   rgba(155, 105, 255, 0.18);
  --aito-muted:    rgba(240, 240, 240, 0.55);
  --aito-accent:   var(--aito-teal);

  /* spacing rhythm */
  --sidebar-w: 228px;
  --topbar-h: 56px;
  --aito-w: 280px;

  /* fonts */
  --font:  'Nunito', sans-serif;        /* per demo */
  --serif: 'DM Serif Display', serif;   /* per demo */
  --mono:  'JetBrains Mono', monospace; /* shared */
}
```

Per-demo palette choices on record:

| Demo | Nav bg | Main bg | Accent | Sans | Display |
|---|---|---|---|---|---|
| accounting | `#0c0f0a` (warm black) | `#f8f6f0` (cream) | `#d4a030` (gold) | DM Sans | DM Serif Display |
| erp | `#0c0f0a` | `#f8f6f0` | `#d4a030` (gold) | DM Sans | DM Serif Display |
| ecommerce | `#1B4332` (dark forest green) | `#F5F7F5` (mint) | `#F5A623` (warm yellow) | Nunito | Nunito |

The accounting and ERP demos share the gold/cream/black scheme —
they're the same B2B-CFO target. Ecommerce intentionally diverges:
zooplus-inspired forest-green sidebar with a warm yellow CTA, more
playful sans-serif, lighter overall feel for the consumer-adjacent
audience.

---

## 9 — Public-demo deployment

Set `PUBLIC_DEMO=1` in the deployed environment to enable the
"showing this URL to a stranger" mode. The flag is shared across all
demos and toggles five behaviours:

1. **CORS lockdown** to origins in `CORS_ORIGINS` (comma-separated).
2. **Three-tier rate limiting** (per-IP, per-tenant, global) — caps
   configurable via `RATE_LIMIT_PER_IP` / `RATE_LIMIT_PER_TENANT` /
   `RATE_LIMIT_GLOBAL`. Localhost bypasses per-IP.
3. **`/api/schema` returns 404** — don't leak the Aito table layout.
4. **`/api/tenants`** (when present) returns just IDs, no Aito URLs.
5. **Memory-only cache** — `init_persistent_cache` becomes a no-op so
   the demo works with a read-only Aito API key. Cold cache after each
   restart is acceptable.

**Submission sanitisation.** When demos accept user input (Smart Entry
form, Pattern Explorer dropdowns, etc.), public mode adds:

- TTL-bounded queue (1h)
- 50-entry FIFO cap
- Per-field length clipping
- Control-char stripping
- EUR amounts clamped to `[0, 1_000_000]`

Submission queue lives in memory only; nothing user-typed is ever
persisted to Aito.

**EU hosting only. No PII stored.** Customer IDs are anonymous (e.g.
`CUST-00123`). The Aito panel footer surfaces this:
`EU hosted · No PII stored`.

---

## 10 — Testing convention

Two layers:

### 10.1 `pytest` for service modules

Standard unit tests. The naming convention is the documentation:

```python
def test_predict_returns_top_account_for_known_invoice_pattern(): ...
def test_predict_marks_low_confidence_when_vendor_is_unseen(): ...
def test_recommend_excludes_already_purchased_skus(): ...
```

A reader skimming the test file should learn how each Aito endpoint is
used in this domain, in order.

### 10.2 `booktest` for review-driven regression

`booktest` (Antti's framework) is the right tool for testing
prediction quality where assertions are stupid but human review is
cheap. Stored under `book/` and `books/` in `aito-accounting-demo`;
runs as part of `./do test`.

The pattern: capture model output for a fixed set of inputs into a
markdown book, review it once, regenerate it whenever Aito query
shapes change. Diffs go through PR review.

This is the canonical solution for the "AI is testable when behaviour
is reviewable" position — and it's a credibility signal in itself for
the OSS reference role.

### 10.3 Adversary Playwright agent

`./do verify <feature>` runs a separate CC instance with Playwright
tasked with **breaking** the feature, not confirming it. Outputs go to
`docs/verification/<feature>.md`. Merge is blocked until the report
exists.

The adversary gets the ADR acceptance criteria, the running app,
Playwright with screenshot/DOM-snapshot helpers. Its report includes
steps attempted (with edge cases and invalid inputs), screenshots at
key states, observed Aito requests/responses, and either failure
paths found or an explicit "no failures found after trying: [list]".

### 10.4 `./do aito-check`

Sanity assertions that run against the PoC dataset:

- Response structure matches expected shape
- Probabilities in `[0, 1]`
- Recommendations non-empty for known-good inputs
- Predictions contain expected fields
- No silent null / empty-list returns where data should exist

Whenever a service adds a new Aito query pattern, it must add the
corresponding sanity assertion in the same PR.

---

## 11 — `aito-cheatsheet.md` — the shared developer guide

Every demo has `docs/aito-cheatsheet.md`. It documents *every* Aito
query pattern the project uses with: the endpoint, the body, the
response shape, the gotchas. The autonomy rules say CC cannot use a
new Aito pattern autonomously unless it's already documented in the
cheatsheet — so the cheatsheet grows organically and becomes the de
facto developer guide.

The cheatsheets across demos share material; consolidate to a shared
reference once a third demo confirms a pattern.

---

## 12 — README structure

Three audiences. Maintain this section order:

1. **What this is** — 2–3 sentences. What the demo does, that it
   demonstrates Aito.ai, link to Aito docs.
2. **See it in action** — screenshot or GIF of the demo path.
3. **Try it now** — a single curl that hits Aito with the free-tier
   key and returns a prediction in ~30 ms. Concrete value, no signup.
4. **The end-to-end workflow loop** — two screenshots that show the
   submit-then-route loop. The whole demo in two images.
5. **What's inside** — one section per view, with a screenshot, a JSON
   body of the actual Aito query that drives it, a one-paragraph
   explanation, and links to the implementation file and the
   per-feature `docs/use-cases/<n>-<view>.md`.
6. **Quick start** — clone, configure, run. Under 5 steps. Must work.
7. **How it works** — architecture overview: app ↔ Aito data flow,
   which Aito features are used and why.
8. **Project structure** — directory guide for code readers.
9. **ADRs** — link to `docs/adr/` with one-line summaries.
10. **Learn more** — links to Aito docs, blog posts, related demos.

---

## 13 — What to vary per vertical, what not to

**Vary** (vertical character):

- Persona name(s), customer profiles, supplier roster, SKU vocabulary
- Brand mark, store name, tagline
- Sidebar palette and accent (within the token system)
- Sans / display font choices
- View list and grouping
- Data model
- Per-view Aito-panel content (`panel-content.ts`)
- Demo-script narrative

**Don't vary** (cross-demo consistency):

- The Aito panel — colours, typography, layout, behaviour
- The token *names* in `globals.css` (the values can vary)
- Endpoint badges and labels (`_predict`, `_relate`, `_recommend`,
  `_search`, `_match`, `_evaluate`) — same vocabulary everywhere
- The five prediction primitives (PredictionBadge, ConfidenceBar,
  WhyTooltip, PredictedField, LiftHint)
- The error envelope shape
- The `do` script verbs
- The `PUBLIC_DEMO=1` deployment behaviour
- The README structure
- Confidence-tier thresholds (0.50, 0.80)
- Latency-badge display
- The `EU hosted · No PII stored` footer line

When a demo wants to vary a "don't vary" thing, propose it as an ADR;
if accepted, it becomes a change to *this document* and propagates
to every other demo, not a one-off divergence.

---

## 14 — Patterns to lift verbatim

To bootstrap the next demo (e.g. `aito-ecommerce-demo`), copy these
files from `aito-accounting-demo` and adapt the interior:

| File | Adapt | Don't touch |
|---|---|---|
| `src/aito_client.py` | maybe trim methods you don't use | error shape, retries, logging |
| `src/cache.py` | — | structure |
| `src/rate_limit.py` | tier limits | shape |
| `src/config.py` | env keys | shape |
| `src/data_loader.py` | schema and fixture file names | upload sequence |
| `frontend/components/shell/AitoPanel.tsx` | — | everything |
| `frontend/components/shell/TopBar.tsx` | brand mark, store name | layout, breakpoints |
| `frontend/components/shell/Nav.tsx` | section labels, items | structure, footer indicator |
| `frontend/components/shell/ErrorState.tsx` | — | — |
| `frontend/components/shell/LatencyBadge.tsx` | — | — |
| `frontend/components/prediction/*.tsx` | — | all five components |
| `frontend/lib/api.ts` | maybe add fmt helpers | apiFetch, confClass |
| `frontend/lib/analytics.ts` | event names | wrapper shape |
| `frontend/lib/types.ts` | add per-domain DTOs | `AitoPanelConfig` and friends |
| `do` | port numbers, demo-specific verbs | shared verbs |
| `shell.nix` | project name | structure |
| `.env.example` | per-demo defaults | key names |
| `docs/adr/0000-template.md` | — | — |

Adapt:

- `frontend/app/<view>/page.tsx` — one per view, each one a
  `useEffect` to load + render.
- `frontend/lib/panel-content.ts` — per-view configs.
- `src/<view>_service.py` — one service per view.
- `src/app.py` — endpoints (the structure stays, the routes change).
- `frontend/app/globals.css` — full design system, but the token
  *names* stay the same.
- `data/generate_fixtures.py` — completely vertical-specific.

---

## 15 — How to evolve this document

This file is the source of truth when demos disagree. To change it:

1. Open an ADR in the demo where the change is needed (e.g.
   `aito-ecommerce-demo/docs/adr/0007-aito-panel-mobile-fab-position.md`).
2. If accepted, update the relevant section of this document in the
   same PR.
3. File follow-up tasks against the other demos to bring them into
   line. Don't let a divergence sit indefinitely.

The point of this document is consistency, not constraint. When a
demo discovers a better pattern, push it back here; when this file
is stale, that's a bug.
