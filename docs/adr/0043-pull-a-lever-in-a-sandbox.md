# ADR 0043: Pull a lever in a sandbox, and watch the shop react

**Status:** Accepted (2026-10-24; Antti's brief for the Ambientia demo via the CRO; the
CPO's sandbox design)
**Date:** 2026-10-24
**Deciders:** Antti

## Context

The partner demo has to *show* actionability, not describe it. The owner sets an offer on
a product (or a review arrives), the estimates change at once, and the shop a shopper
sees changes with them. Today every view is read-only, and the Shop can't react to a
product's state:

- The Shop recommends `product_sku`. A product's monthly state (offer, stars) enters only
  as history. ADR 0032 tried recommending `product_state` instead; the B5 sweep found it
  ties on hit@10 and calibrates worse. A state row with no impressions gets a near-zero
  `$p`, so a freshly discounted product would sink, not rise.
- Writing anything needs a write key. Master serves the public demo and must never be
  written by it.

The CPO's answers (2026-10-24):
- v2 has no cheap env clone, so a sandbox is an env loaded by our own loader from the same
  fixtures as master.
- Antti creates it and its read-write key, scoped to that env only, and puts the key in
  the server's config himself.
- After a write, the first predict rebuilds only the new segment (fast). The first
  predict after a load is the slow one, so warm up after every load.

## Decision

### Sandbox mode, failing closed

- **Two clients:**
  - **master:** its usual key, and it never writes. Any write method raises. Cache writes
    stay off, as with `PUBLIC_DEMO=1`.
  - **sandbox:** `AITO_SANDBOX_ENV` + `AITO_SANDBOX_API_KEY`. It exists only when both are
    set and the env name starts with `sandbox`; otherwise sandbox mode is off and the
    lever endpoints answer 404.
- **Lever writes go only through the sandbox client.** A test asserts that no write path
  can reach the master client.
- **The browser holds the mode.** "Sandbox mode" in the header sends every read and write
  of the session to the sandbox env, with a banner: "Sandbox: your changes go to env
  `sandbox`. Reset". Leaving the mode returns to master. Reading the sandbox goes through
  its own client too, so what the room sees after a lever is the sandbox's data.
- **Reset** reloads the sandbox from the release fixtures (`./do sandbox-reset`), then
  warms it up. With two envs (`sandbox`, `sandbox-b`), the button can swap to the
  already-warm one instantly while the other reloads.

### The levers write next month's state

The data ends in 2026-04. A lever writes the product's **2026-05** `product_states` row
(insert or replace): price, list price, discount, offer and band, with stars from the
reviews so far. It never rewrites a past month: that would relabel history's impressions
and change what Aito learns from them. The Shop in sandbox mode shows 2026-05.

- **Offer:** the owner picks a band (none, 10–15, 15–20, 20+); price and discount follow
  from the list price.
- **Review:** the owner adds a review (stars, text). The 2026-05 `rating_band` is
  recomputed from all reviews, with the same rule as the generator
  (`data/shoppers.py: rating_band`). When one review doesn't change the band, the view says
  so; it doesn't pretend.
- **Read back before showing the reaction.** After a write, the app reads the row back from
  the sandbox and shows the reaction only from what was read.

### What the owner sees after a lever (Product view)

- **The chance a showing ends in a purchase,** per discount band: the calibrated discount
  what-if (`src/discount_what_if.py`), with `$why`: the band's lift (shop-wide) and the
  product's own. The new band is marked.
- **Demand next month:** `_estimate units` with the state's band in `where`, probed before
  use. If the band doesn't enter the estimate, only the units what-if by price is shown,
  and the view says the discount isn't in the units model.
- **Who it reaches:** the Shop personas for whom the product now ranks higher, linked.

### How the Shop reacts, honestly

The Shop keeps its measured ranking (ADR 0033, K+) for the candidates, then re-scores its
top 40 by the next-month state:

    score = $p (the Shop's _recommend) × lift(offer band) × lift(rating band)

The lifts are Aito's, read from `$why` of `_predict purchased` on impressions with the
state's bands. They're shop-wide (the same for every product), and fetched once per page,
not per product.

- A product whose next-month state differs from "no offer, the same stars" gets a reason
  chip: "On offer ×1.8, learned across the shop" (or "4 stars ×1.15").
- The grid shows the rank change when the state changed in this session ("↑ 7 since the
  offer").
- **Honesty rule:** the multiplication is a modelling choice of this app, not a single
  Aito query. The Shop's panel says so and shows both factors. It's off outside sandbox
  mode, so the public Shop keeps its measured ranking.

### The agent on the sandbox

`aito-mcp` with `AITO_URL` = the sandbox database (see the amendment) and a read-only key that can read it. The agent
sees the 2026-05 state the owner just set (ADR 0042's lever tools can follow).

## Aito usage

| Shape | Status |
|---|---|
| `_predict purchased`, `where {product_sku, product_state.discount_band}` | in the cheatsheet (PR #70) |
| the same with `product_state.rating_band` | probed before use |
| `_estimate units` on monthly_sales with `product_state.discount_band` | probed before use |
| writes: `POST /data/product_states` (one row), `POST /data/reviews` | v2 data API, probed on the sandbox before use |
| read-back: `_search product_states where {product_state_id}` | known form |

## Acceptance criteria

- [ ] With no sandbox key configured, every lever endpoint is 404, and no code path can
      write to master (test).
- [ ] In sandbox mode, setting a 20 %+ offer on a guinea-pig product reads the row back,
      updates the estimates with `$why`, and, in the guinea-pig shopper's Shop for
      2026-05, shows the product with its offer chip and its rank change.
- [ ] Adding a 1-star review that changes the band lowers the product's score by the
      band's lift. One that doesn't change the band is reported as "no change in its star
      band".
- [ ] Reset returns the sandbox to the release data, and the first predict after it runs
      at the warm-up's speed.
- [ ] The full lever → shop loop is timed 5× on the demo machine. The run sheet records
      the times.

## Demo impact

The partner demo's centre: Flow 1, the guinea-pig shopper's kit path; Flow 2, pull a
lever, see the estimates, then the shop react; Flow 3, the agent sees the change. The run
sheet is `docs/demo-script.md`'s new section.

## Out of scope

- Per-visitor sandboxes on the public demo. Writes there would need per-visitor envs and
  a write key on the public server.
- Levers beyond offer and review (labels, stock: ADR 0038's data).
- Measuring the re-ranked Shop; it is a demo device, labelled as such. Its evaluation
  would be an Evidence entry of its own.

## Consequences

**Good:**
- The owner's action and the shopper's experience are visibly one system.
- Master stays read-only by construction.

**Bad:**
- The re-scored Shop is not the measured Shop. It is labelled, and off outside the
  sandbox.
- Sandbox resets cost a reload; two envs hide it.

## Amendment (2026-10-24, the CPO's review, before any code)

**Keys are per database on shared.aito.ai, so the sandbox is its own database, not an env
under PetNord's.** A key authenticates only under its own `/db/<name>/` path. A wrong key
there shows up as a misleading 405. An env under PetNord's DB could only be written with
PetNord's read-write key, which also writes master.

- **The sandbox:** database `aito-ecommerce-sandbox`, plus `aito-ecommerce-sandbox-b` for an
  instant reset. Each has its own read-write key and, if the console issues one, its own
  read-only key.
- **Config:** `AITO_SANDBOX_URL` (`https://shared.aito.ai/db/aito-ecommerce-sandbox`) and
  `AITO_SANDBOX_API_KEY`. The second fence is that the URL's database name must contain
  `sandbox`; otherwise sandbox mode stays off.
- **Master, in the demo run, is read with PetNord's read-only key.** So master is
  read-only by the key, and not only by the code. The code fence (the master client
  raises on any write) stays.
- **Flow 3's agent** gets the sandbox's read-only key. If there is none, its tools are
  read-only by construction (aito-mcp refuses writes unless started with
  `AITO_MCP_ALLOW_WRITES=1`).

**Never carry `$why` across an override.** A re-scored Shop item shows the explanation of
its *adjusted* score: Aito's factors from the Shop's query, then the explicit lines
"offer band lift ×1.8 (shop-wide)" and "star band lift ×1.15 (shop-wide)", so the
explanation still multiplies out to the shown score. It never shows Aito's `$why` beside
a number Aito didn't produce.

**Sunday's checks:**
- time the load and the reset; if a reset is over about 20 s, the button swaps to
  sandbox-b;
- time the lever → reaction loop 5×, reading back after each write;
- if `_estimate` with the state is flaky in any of the 5 runs, drop it to the units
  what-if by price instead of debugging on Monday.

Reset loads the release fixtures only.

## Amendment 2 (2026-10-24, Antti's request; the CPO's correction), before the code lands

**One sandbox becomes a temporary env per session, branched from a template.** Aito v2
has instant copy-on-write env branches:
- `POST /db/{db}/api/v2/_envs {"name": …, "basedOn": "env.master"}` creates one in
  milliseconds, with no load;
- an env is chosen only by the URL path `/db/{db}/env/{name}/api/v2/…`.

- **Template:** the sandbox database's master, loaded once from the release fixtures
  (`./do sandbox-template-load`). PetNord's database stays read-only to the demo. Keys are
  per database, with no env-scoped keys, so the sandbox database's read-write key can
  never reach PetNord.
- **Temp env:** `tmp-YYYY-MM-DD-HH-MM-SS-<16 hex>`, the hash 64 bits from `secrets`.
  - "New sandbox" creates one (an admin-token endpoint; 404 without a configured token).
  - The client carries it as `?db=<name>` (shareable for a meeting) or `X-Aito-Env`. The
    backend maps it to the env path.
  - A name that doesn't match the pattern exactly, or isn't in the env list, is refused
    (400). It never falls back to a master.
  - Writes go only to `tmp-` envs, never to the template.
- **Reaper:** at startup and every 10 minutes, it deletes `tmp-` envs older than 3 hours
  (age from the name; a malformed name is logged, never deleted). At most 5 live temp
  envs; "New sandbox" answers 429 beyond that. "Reset" means a new branch.
- **The banner says so:** a sandbox starts from the release data (the template), not
  from live master.
- **Open, measured by Aito core before the first live run:**
  - whether one write to `product_states` (a rep1 link target of impressions,
    order_lines and monthly_sales) relinks those tables in the branch, and at what cost;
  - the first predict after a write.

  If a write costs seconds, the template gets every product's 2026-05 row in advance,
  and a lever only replaces its values.
- **Fallback for Monday:** if the branch flow isn't rehearsed by 10:00, one fixed temp
  env created in advance serves the demo.
