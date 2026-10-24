# Run sheet: Ambientia, Mon 26.10 15:30 (Helsinki)

The script, its numbers and their sources: `docs/demo-script.md`. This page
is what to do before and during the run. Helsinki is UTC+2 from Sunday
25.10, so sandbox branch names, which carry UTC, read two hours behind the
clock.

## Pre-flight

**Sunday (Antti):**

1. `./do sandbox-template-load` once. Then `./do sandbox-time`: write the 5
   timings of the lever → Shop loop here: ____ ____ ____ ____ ____.
2. Rehearse all three flows on a fresh branch. Tick each **(Sunday)**
   number in the script, or correct it.
3. Rehearse Flow 3 (below). Keep the transcript.
4. If `_estimate` with the state was flaky in any of the 5 runs, keep the
   units what-if by price (the script already uses it).

**Monday:**

| When | What |
|---|---|
| by 10:00 | If the branch flow isn't rehearsed by now, fall back to one fixed branch made in advance (ADR 0043, amendment 2). |
| 14:30 | Start the app with the sandbox config: `AITO_SANDBOX_URL`, `AITO_SANDBOX_API_KEY`, `ADMIN_TOKEN`. PetNord's key is the read-only one. |
| 14:45 | `./do sandbox-new`: it prints the `?db=` link. This is the spare. A branch lives 3 hours, so one made at 14:45 lasts until 17:45, past the meeting; make it no earlier than 13:45. |
| 14:50 | Warm-up: click Flow 1 and Flow 2 on the spare link, without pulling a lever. `./do sandbox-list` shows it live. |
| 15:00 | `./do agent-demo <spare branch>`: ask one question, check the first answer, then quit. |
| 15:20 | The DNS check below. Open the tabs: `/shop/?shopper=paivi`, the spare link, a terminal in the repo. |

**DNS margin.** This laptop's DNS lookups can take 5 s. The app keeps its
Aito connections open for 5 minutes (`src/aito_client.py`,
`keepalive_expiry=300`), so a pause longer than that costs one slow
reconnect. Click something in the app at least every 4 minutes while
talking. Measure: `curl -s -o /dev/null -w '%{time_namelookup}\n'
https://shared.aito.ai/`. Optional for the day: pin the host in
`/etc/hosts` with the address `getent hosts shared.aito.ai` gives, and
remove the line on Tuesday (the address can change).

**Idle branches.** Aito evicts an env idle for 30 minutes from memory. The
app re-warms a branch idle for 25 minutes on its next request, which costs
that request some seconds. The 14:50 warm-up plus clicks keep it warm.

## The flows

| Flow | URL | Lands on |
|---|---|---|
| 1 Shopper | `/shop/?shopper=paivi` | Kit: PetNord Hideout 17 %, Trixie Hideout 15 % |
| 2 Lever | New sandbox, then `/product/?sku=SKU-PT-0563&month=2026-05&tab=what-if&db=<branch>`, press **20 % or more off** | Read back "May 2026, 20 % or more off, €17.27, 4 stars" |
| 2 Shop | **See the Shop react, as Päivi →** (`/shop/?shopper=paivi&month=2026-05&db=<branch>`) | Trixie Hideout 1st, "Score 48 ↑ 9 since the offer", "On offer ×1.8" |
| 2 Variant | a 1-star review on the same product; the honest case `?sku=SKU-PT-0558` with 5 stars | 4 → 3 stars ×0.83; "No change in its star band" |
| 3 Agent | `./do agent-demo <branch>` | It reads the May row and the per-band estimates |
| Evidence | `/evidence/`, then **Business reorders** | The claim, word for word |

## Flow 3: the agent's setup and rehearsal

- **Key:** the sandbox database's read-only key, as one line in
  `~/.config/aito-mcp/sandbox-readonly-key` (chmod 600). `./do agent-demo`
  refuses without it and never prints it. If the console issues no
  read-only key for the sandbox database, decide before Monday. With the
  read-write key in that file, aito-mcp's refusal of writes is the only
  fence; without a key, skip Flow 3 and play the video.
- **What runs:** Claude Code in an empty temporary folder, with
  `aito-mcp@1.2.0` as its only tools (`scripts/agent-demo/aito-mcp-sandbox.sh`),
  `AITO_URL=https://shared.aito.ai/db/aito-ecommerce-sandbox/env/<branch>`.
  Bash, files and the web are off. `AITO_MCP_ALLOW_WRITES` never reaches
  the server, and the write tools are disallowed as well.
- **The brief:** `scripts/agent-demo/brief.txt`, disclosed in full if
  asked. It says: read-only, propose and don't act, quote only numbers the
  tools returned, say when the evidence is thin. Two lines cover reading
  an offer's effect and Aito's 1/52 floor; a third says May's rows are the
  owner's plans, with no showings yet.
- **Rehearsal:** `./do agent-demo <branch> "What has the owner set for May,
  and what would an offer do for those products?"`. Check each number it
  quotes against the Product view. Expected: the May row (20 %+ off,
  €17.27); 10.6 % at no discount and 19.7 % at 20 %+; the lift called
  shop-wide; 5 showings at 20 %+ called thin. A run that adds its own
  arithmetic or misnames a product is a reason to ask again, not to go on
  stage with it.
- **Questions not to take live:** churn (the newest months' labels have no
  follow-up yet, and the answer names generated customers).

## Fallbacks

- **Video:** `.ai/deck-ambientia-2026-10-26/agentic-demo.mp4` (68 s, two
  real agent runs on the same data, recorded 2026-10-24).
- **Static screenshots** (same folder): `discount-what-if.png`,
  `discount-what-if-unseen-bands.png`, `shop-analytics-state-lifts.png`,
  `uci-business-reorders.png`, `agentic-q1-offers.png`,
  `agentic-q2-gate.png`.
- **No sandbox at all:** run Flow 1, the Product view's decision on the
  public data (`/product/?sku=SKU-PT-0563`), the video, then Evidence.

## Say aloud

1. "Everything on the PetNord screens is generated data with planted
   effects. It shows how Aito works, not how much it would lift your
   shop."
2. "The offer's lift is shop-wide: what a discount does across all
   products, not this product's own response."
3. "The re-scored Shop multiplies Aito's probability by Aito's lifts. That
   multiplication is this app's choice, and the score isn't a rate."
4. "The agent proposes, and a person decides. Its judgement varies from
   run to run."
5. "The real-data number is the top suggestion for buyers with one or two
   earlier orders. For regular buyers it ties the best simple method; with
   no history it equals popularity."
