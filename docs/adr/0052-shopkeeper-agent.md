# ADR 0052: The shopkeeper agent — routine runs with a confidence gate and an approval step

**Status:** Accepted (2026-10-31, Antti: "merge it and implement it"). Slice 1 built and merged (#138, fixed forward in the follow-up): the gate, one stored win-back run, the Board, the view, the Retention link.
**Built, differing from the plan:** approvals and edited settings live in the browser, so there is no `agent_runs` / `agent_steps` log and no approvals table; the Board holds findings about thin evidence, approval load and churn drivers, not yet findings about action kinds against their baselines.
**Not built:** the stock-aware check, portfolio, product-entry routines; live questions; the Toolbox switch; scheduled running; a server-side approve/reject log.
**Seen in the stored run at the recommended settings:** 8 acted, 2 suggested, 2 needing a person, 8 quiet: "suggest" appears for only 2 of 20 customers, so the middle band of the gate is thin in this data.
**Date:** 2026-10-31
**Deciders:** Antti

## Context

"Ask the store" (ADR 0042) answers a question: an agent calls the app's lever services as read-only
tools and says what the data supports. A shopkeeper's week is not questions. It is a few
recurring jobs: win back customers who are drifting, check stock, enter new products. Merchants
told us three things about agents in this setting:

- **Trust is the issue, not capability.** An agent that "succeeds" and is wrong is worse than
  one that does nothing. The useful agent knows when not to act.
- **Admin work is what they want automated.** Open-ended chat is secondary.
- **A run has to show what it earned.** Euros added over doing nothing, per run.

Two measurements limit what we may claim:

- Per-product demand forecasts tie the naive method, so no routine is headlined by a forecast number.
  Purchasing is a ranked reorder / overstock list.
- On the ERP matching benchmark a text-search baseline beats Aito at top-5. We claim the gate, not
  better matching.

The levers already exist as services: ranked retention actions (ADR 0051), the markdown proposal
(`src/markdown_proposal.py`), the discount what-if, the Supply queues, the product-filling suggestions.

## Decision

A new view, **Shopkeeper**. Three columns of navigation, one reading pane:

- **Board** (left, first): the shop's list of systematic improvements, each with its evidence, owner (agent or
  shopkeeper), status and the run or conversation that raised it.
- **Agents and runs** (left, second): the routines, their schedule (they may roll automatically) and their latest runs.
- **Past conversations** (left, third): every stored run and every question asked.
- **Reading pane** (right): the selected run or conversation, as a list of steps; each step is a tool call, its result
  and one of four outcomes.

### The gate (the product)

Every proposed action carries its lift over no action, how many past rows match the customer's exact situation and action, and the threshold in
force, shown on the step. The lift is Aito's estimate over the whole action table; the matching rows are a check that the situation has history, not what the lift rests on:

| Outcome | When | Effect |
|---|---|---|
| **Act** | confident (`$p` at or above the store's threshold) and the evidence is not thin | executed, if the routine allows it |
| **Suggest** | between the thresholds | queued for the shopkeeper's approval |
| **Stay quiet** | no evidence, or the "thin" rule of ADR 0042 applies | nothing is proposed; the step says why |
| **Never auto** | a kind the store marks as always needing a person | always queued, whatever the confidence |

**The thresholds and the "never auto" kinds are the store's settings,** with recommended defaults the app proposes
(and the evidence for them), not constants the demo imposes. They are shown on every step. Nothing in the demo changes
real data. As built in slice 1, "act" is a label on a stored run, and a shopkeeper's approvals and edited settings live in the
browser, so no table is written; the simulated log tables of the plan wait for the live routines.

### One win-back record

There is one win-back dataset and one record of its actions and outcomes (ADR 0051's `customer_actions`, shown by
`/winback` and Retention). The agent does not keep a copy: its runs read that record and write their actions to it, so a
run is built from the snapshot Retention serves and marked stale when Retention serves different numbers (a digest of the numbers it read). A run may roll on a schedule (not built).

### Two learning loops

1. **The statistical loop** is Aito: the next best action per customer, from the actions already taken and what followed.
2. **The agent's loop** sits above it and works on the configuration. After a run it reads the outcomes of the actions
   taken and asks whether the configuration, not a single customer, is the problem: which action kinds, parameters
   (voucher depth, send timing) or segments underperform their baseline, and why (`_relate` on the outcome, scoped to the
   segment). It proposes a change to the action configuration, never makes one: the proposal goes onto the Board.
   The same root-cause step runs on the other routines (a product group with returns, a supplier with late deliveries).

The Board lists these findings as a to-do list for the shop. A finding says what it rests on and what was tried.
We do not claim that the second loop improves results until a configuration change has been measured.

### Routines (build order)

1. **Weekly win-back run.** Reads the win-back record; for each at-risk customer takes the ranked actions (email,
   voucher, ad or none) with cost and expected euros over no action. Confident ones are acted on, unsure ones queued.
   The run ends with the action loop: which actions were taken, who was saved. Then the agent's learning loop.
2. **Stock-aware morning check.** Reorder and overstock ranked from the Supply service; out-of-stock items kept off
   recommendation lists; overstocked items proposed for a markdown with its margin impact.
3. **Portfolio management.** The agent reviews the range: products to retire (low sales, low reviews, high
   returns), with the stock and the margin at stake; products to add; and prices. For pricing it uses what we have
   (price what-if, price curve, markdown proposal) to propose a price change with the units and profit it implies,
   always as a decision for the shopkeeper. *New products from suppliers or competitors needs data the demo does not
   have* (supplier offers, competitor prices): it would be simulated and labelled, a data release of its own (see Notes).
4. **New-product entry.** Name typed; the other fields suggested from similar products, accepted when confident, flagged
   when not.

Each run ends with **"euros added vs doing nothing"**, summed from the steps that used it, and the number of steps
acted on, queued and left quiet.

### Pre-generated runs and live questions

- Runs and conversations are generated by a script from the live services, stored as data (`data/agent_runs/`), and
  shown as history. Every number in a stored run is a field of a tool result and is recomputed by a test (the
  claims-checklist approach); a stored run records its data release and fails the test when the release changes.
- A free-form question reuses the ADR 0042 agent and tools, labelled live, with a cost cap and the stored runs as
  fallback when no model key is configured.
- A **Toolbox** switch turns the Aito tools off, so the agent has to guess and says so.

## Aito usage

No new query shapes. Tools wrap existing services:

| Tool | Wraps |
|---|---|
| `retention_candidates()`, `ranked_actions(customer)` | `retention_actions.ranked_actions_for` (`_predict` over `customer_actions`, ADR 0051) |
| `reorder_queue()`, `overstock()` | the Supply service |
| `markdown_proposal(sku)` | `markdown_proposal.propose_markdown` |
| `offer_what_if(sku)` | `discount_what_if.get_discount_what_if` |
| `suggest_fields(name)` | the product-filling service (`_predict` per field) |
| `price_what_if(sku, price)`, `price_curve(sku)` | `price_what_if`, `price_curve` |
| `root_causes(outcome, segment)` | `_relate` on the outcome, scoped with `$on` |

New tables: the simulated logs (`agent_runs`, `agent_steps`), the Board's items and the store's gate settings. An availability-conditioned demand read (does demand differ
when stock is low?) is a separate ticket (td-20261030080248329856); this ADR makes no urgency claim until it is measured.

## Acceptance criteria

- [x] A user can open the Board, the routines and the past conversations, and the reading pane shows the selected one.
- [x] A user can open a stored win-back run and see, per customer, the ranked actions, the chosen
      outcome (act, suggest, stay quiet, never auto), the threshold, the `$why` and the euros over no action.
- [x] The run's "euros added vs doing nothing" equals the sum of the acted-on steps, and a test recomputes it.
- [x] A customer with no evidence gets "stay quiet" with the reason, not a guess.
- [x] The thresholds and "never auto" kinds are editable in the store's settings; the steps change outcome accordingly and show the values in force.
- [x] A kind marked "never auto" is never executed without approval, whatever the confidence.
- [x] A run is built from the snapshot Retention serves, and is marked stale when Retention serves different numbers.
- [ ] After a win-back run the Board holds at least one finding with its evidence (an action kind, parameter or segment against its baseline). (The Board's findings are thin evidence, approval load and churn drivers; none yet compares an action kind with its baseline.)
- [ ] A portfolio run proposes retiring products with the stock and margin at stake, and a price change with the units and profit it implies, both as decisions awaiting approval.
- [ ] A user can approve or reject a queued step; the log shows it, labelled simulated. (Approve and reject work in the browser; there is no log.)
- [ ] With the stock filters on, no recommendation list in the stock-aware run shows an out-of-stock product (asserted by `aito-check`).
- [ ] The Toolbox switch makes the agent say it is guessing and drops the "act" outcome.
- [x] A stored run recorded under another data release, or from other numbers than Retention serves, is marked stale (tested).
- [x] No page copy names a prospect or states a price (a test checks the stored run for prospect names).

## Demo impact

A new moment in `docs/demo-script.md`: the weekly win-back run. Existing moments are unchanged.
The Retention view links to the run that uses it; Supply gains one when the stock-aware routine exists.

## Out of scope

- Any claim that the agent matches products or forecasts demand better than a baseline.
- Real sending of messages or placing of orders.
- Urgency or "few left" effects, until the availability measurement exists.
- Message classification and employee routing (ADR 0051, later slice).
- A multi-agent setup or agent-to-agent protocols.

## Consequences

**Good:**
- The trust story is something a person can read step by step, with numbers they can check.
- The agent reads the numbers the views serve, and a run is marked stale when they differ.

**Bad:**
- A new surface to keep current; stored runs go stale on every data release and the test will say so.
- The "never auto" and threshold choices are judgement calls that need Antti's sign-off.

## Notes

- Open questions: the recommended defaults for the gate and what evidence we show for them; whether stored runs are
  regenerated in `./do promote`; the supplier-offer and competitor-price data for portfolio additions (a simulated
  data release, labelled, with its preregistration), and whether pricing decisions can be tested against the
  planted price effects before any claim is made.
- Builds on ADR 0042 (tools, evidence block, thin rule) and ADR 0051 (ranked actions).
