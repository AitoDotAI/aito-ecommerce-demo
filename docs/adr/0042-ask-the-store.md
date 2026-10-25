# ADR 0042: Ask the store — the levers as agent tools

**Status:** Accepted (2026-10-24, Antti: "the actionability of the database and agents
should play very nicely together", and his delegation of the unified release)
**Date:** 2026-10-24
**Deciders:** Antti

## Context

For the Ambientia deck (2026-10-24) we ran a merchant's AI agent (Claude Code) on the
PetNord data through Aito's MCP server (`aito-mcp`, read-only). Four rehearsed questions,
about 15 runs, each answer checked by hand against the data (CAVEATS.md in the deck
folder). What we learned:

- **Aito's answers carry the agent's evidence.** Every answer has a probability, the
  reasons (`$why`) and the rows it rests on. So the agent could say "17 % → 26 %, from 72
  impressions" and, for a price rise seen in 7 views, "the data can't tell". That second
  kind of answer, the gate, is what makes an agent safe to act on.
- **A what-if is a query.** "If this product were 20 % off" is one `_predict` with a
  changed condition; the agent tried levers product by product in seconds.
- **Every error came from raw tables, never from a number Aito computed:**
  - its own arithmetic ("1–11 units a month" when two months had 0);
  - a misread calibration floor ("offers don't help" for a product at Aito's 1/52 floor);
  - a different query than the app's for the same question (39 % vs the app's 46.9 %);
  - a wrong product name.
- **Its judgement varied between runs on the same data.** One run put a product on offer;
  another said "no offer needed: 3.7 months of stock". Both are defensible, which is
  exactly why the agent proposes and a person decides.

The app's owner views (ADR 0041: Product, Supply, Retention) already compute these levers
correctly, with calibration checks and honest copy. The agent and the views should be one
product: the agent proposes, each proposal opens the view where a person checks and acts.

## Decision

### 1. The levers as tools

A second MCP server in this repo, `petnord-levers` (stdio, read-only). It wraps the app's
own services, the same code the views call, so an agent and the UI can't disagree:

| Tool | Wraps | Returns |
|---|---|---|
| `offer_what_if(sku)` | `src/discount_what_if.py` | chance a showing ends in a purchase per discount band; the band's lift (shop-wide) and the product's own; views and purchases per band; `calibrated` |
| `price_what_if(sku, price)` | `src/price_what_if.py` | units, revenue, profit next month; contributions in units |
| `reorder_queue()` | the Supply service | SKUs to reorder now, with revenue at risk and the forecast's contributions |
| `overstock()` | the Supply service | tied-up capital per SKU, with markdown proposals |
| `at_risk_customers()` | the Retention service | at-risk customers (latest month with a known label), with drivers and the win-back offer |
| `find_products(text)` | `_search products` | SKU, name, category, current state |

**Every result carries the same evidence block:**
- `estimate` and its `why`;
- `rests_on`: the row counts behind it;
- `thin`: true when a pre-set rule says the evidence is too little. Examples: fewer than
  30 rows of this product in the band, Aito's calibration floor, or a label without its
  follow-up yet. The rule lives in one module and is tested;
- `view`: the URL of the view that shows the same numbers, with the what-if prefilled
  (e.g. `/product?sku=SKU-PT-0287&band=20%2B`).

**The agent does no arithmetic of its own:** every number it may quote is a field of a
tool result. The raw `aito-mcp` stays available for questions the levers don't cover, and
answers from it are labelled as such.

### 2. Ask the store, in the app

A panel on Overview, also reachable from the header: a merchant asks in their own words
and gets the agent's answer.
- Up to three proposed actions, each with its impact (from the tool), its evidence line
  ("from 72 views", or "thin: 7 views") and **Open →** to the view.
- A **gate** in the copy: when every lever is thin, the answer says so first.
- **Read-only:** the agent proposes and changes nothing.
- **Runs on a server-side agent with the levers server:**
  - The model call is the app's only new external dependency. It's proposed here and
    fixed in the implementation PR: the Claude API, model `claude-opus-5-5`, key server
    side.
  - On the public demo, a small set of rehearsed questions answers from recorded runs.
    Each is labelled "recorded on <date>"; a live box takes free questions only where a
    key is configured. So the demo never depends on a live model in the room, and nothing
    on the page is invented.

### 3. Measured, in Evidence

An Evidence entry, **Agent answers, checked**, synthetic:
- a fixed set of 20 merchant questions, 3 runs each, with and without the lever tools;
- every number in each answer checked automatically against the tools' results and the
  data;
- reported: the share of answers with a wrong number, with a number not from a tool, and
  with a missed "thin" flag, each with its interval.

The CAVEATS.md rehearsal is its first, informal row: zero tool-computed numbers wrong,
four slips from raw tables.

## Aito usage

No new query shapes: the tools call the app's existing services. The evidence block's
`rests_on` uses the counts those services already fetch (`_batch` counts, `$why`).

## Acceptance criteria

- [ ] An agent with only `petnord-levers` answers "which products should go on offer this
      week?" with numbers that equal the Product view's for the same products, and links
      that open those views with the what-if prefilled.
- [ ] A lever result whose evidence is below the rule carries `thin: true`. The agent's
      answer says so (checked in the Evidence run).
- [ ] Ask the store shows recorded answers on the public demo, each labelled with its
      date, and never a live call without a configured key.
- [ ] The Evidence entry reports, with intervals, the error rates with and without the
      lever tools.
- [ ] No tool writes. Each tool's annotation says read-only, and a test asserts it.

## Demo impact

A closing beat for partners, after Product: "Ask the store: which products should go on
offer this week?" The agent proposes two, flags one as thin, and **Open →** lands on the
Product view showing the same numbers. Then the gate question: "did our price rise hurt
sales?" Answer: "7 views; the data can't tell."

## Out of scope

- Writing actions back: setting prices, sending campaigns. A later ADR, with approvals.
- Free-form questions on the public demo without a configured key.
- Agent frameworks beyond MCP plus one server-side loop.

## Consequences

**Good:**
- The agent and the views tell one story with the same numbers; partners can point their
  own agents at the same MCP tools.
- The agent's error rate becomes a measured number, not a hope.

**Bad:**
- A model dependency and its cost. Recorded answers keep the public demo free of it.
- Recorded answers can go stale when the data changes; each release re-records them (the
  ADR 0035 precompute step is the natural place).

## Amendment (2026-10-25, Antti: "we could have that ask button if the LLM is specified … we can use Claude for this, as we now have credits")

**A live Ask button, on when a model key is configured. Built; not yet run against the live model.**

- **On or off.** `GET /api/ask` says `enabled` only when the server has `ANTHROPIC_API_KEY` **and**
  `ADMIN_TOKEN` (the sandbox's). The top bar shows **Ask** only then. Without a key there is
  no button, and `POST /api/ask` answers 404.
- **Who may ask.** `POST /api/ask` needs the admin token in `X-Admin-Token`, asked once per tab
  as for "New sandbox". A question costs credits and goes to an outside service, and ecommerce.aito.ai
  is public, so on a public deploy a question is the presenter's, not a visitor's. Recorded answers
  for visitors remain the plan above, and are not built.
- **The model.** The Anthropic Python SDK (a new dependency, `anthropic`), model `claude-opus-5-5`
  (`ASK_MODEL` overrides), adaptive thinking, effort `medium`, at most 8 rounds of tool calls.
  A refusal, a cut-off answer and a loop that never stops are errors shown to the person, never
  an empty answer. The refusal-fallback beta is not used yet: untested without a key.
- **The tools** (`src/ask_tools.py`) wrap the services the views call: `find_products`,
  `offer_what_if`, `price_what_if`, `reorder_queue`, `overstock`, `at_risk_customers`. Each returns only
  fields of that service's result and a `view` path; `offer_what_if` marks a band shown under 30
  times `thin`. Supply and Retention read the same precompute snapshots as their pages. All read.
  PetNord's database, or the sandbox the request names (`?db=`), is read through the same client the
  views use.
- **The panel** (`AskStore.tsx`) shows the answer with the app paths it names as links (the
  sandbox kept), and under "N Aito queries it rested on" every tool call with its time and any error.
- **Settings:** `ANTHROPIC_API_KEY`, `ADMIN_TOKEN`, optionally `ASK_MODEL`; documented in the
  example settings file. The key is read from the environment and never leaves the server.
- **Tested** against a scripted stand-in for the Messages API (the loop, errors, limits), the tools
  over the views' result shapes, and the routes (off without a key or token, 403, error mapping). The
  first live question is the real check: until then the model call itself is unproven.
- **Not done:** recorded answers, the "Agent answers, checked" Evidence entry, the `petnord-levers`
  MCP server for outside agents, and the `thin` rules beyond the offer bands.
