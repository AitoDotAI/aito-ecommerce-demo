# ADR 0057: The stock routine as a rule, and the first real agent: product entry

**Status:** Part 1 (the stock rule) built; part 2 (the product-entry agent) not yet. Accepted 2026-11-01, Antti: "Go for it" to the order in ADR 0054's follow-up: the stock routine first, then a product-entry agent.
**Built, differing from the plan:** approvals of queued steps and edited settings live in the browser (as in ADR 0052); the stock run adds nothing to the Board; the right-hand Aito panel still shows the win-back's Retention query when the stock run is open.
**Date:** 2026-11-01
**Deciders:** Antti

## Context

ADR 0054 split the Shopkeeper's routines into **rules** (a calculation on Aito's numbers and stored facts, repeatable, no model) and **agents**
(a model reads, writes or orchestrates). Only the win-back rule exists. Two of the routines it lists are labels: *Stock-aware morning check*
(a rule) and *New-product entry* (an agent). The data for the first is already served by Supply: a reorder queue with the stock, the reorder
point, the units sold in the planning window and the order's cost, and an overstock list with Aito's discount sweep.

## Decision

### 1. The stock routine: a rule with its own gate

A stored run, `data/agent_runs/stock.json`, built from the Supply snapshot (`data/precomputed/v2-master/supply.json`), listed beside the win-back run.
One step per SKU in the reorder queue (*order N units for X €*) and one per SKU in the overstock list (*a markdown, or hold*). The same four outcomes
as ADR 0052, judged by a gate of its own, since there is no lift here: the evidence is observed sales, not a prediction.

| Outcome | Reorder step | Overstock step |
|---|---|---|
| **Act** | enough sales behind it, the order is within the limit, and the stock is at or below half the reorder point | – (a markdown is a price change: always a person) |
| **Suggest** | enough sales and within the limit, but the stock is above half the reorder point | Aito's sweep finds a markdown that clears the excess |
| **Needs a person** | the order is above the limit: a large commitment is never the rule's | – |
| **Stay quiet** | fewer observed sales in the window than the evidence bar: nothing to base an order on | the sweep says the markdown would not clear it, or to hold |

**Defaults** (the store's settings, shown on every step, as in ADR 0052): an evidence bar of **5 units sold** in the planning window, an order limit of **500 €**,
the urgent share **0.5**. On the stored Supply snapshot (2026-05) that gives, of 83 reorder steps: 40 act, 2 suggest, 7 need a person, 34 stay quiet (release 4's data; release 3b's gave 45, 2, 5 and 31).
**These are Antti's to set**: they decide what a rule may spend.

Nothing is ordered: a run is simulated, like the win-back's. A reorder line says it uses the simple rule (ADR 0045's observed sales), not a forecast.

### 2. The product-entry agent (the first agent that does something)

A model drafts a new product's entry: the free-text description, and a check of the structured fields against what Aito predicts from similar
products. Its tools are read-only wrappers of the Product filling view's field predictions (`_predict` for each field) and of the catalogue search,
so every field it states is a number or a value a tool returned. It proposes; a person approves; nothing is written.

It is an agent, and so it carries a burden of proof the rules do not: **it has to beat the rule that would do the job without a model.** The rule
is the Product filling view as it is: Aito's predicted fields, and a templated description built from them. The comparison runs on held-out
products (entries the shop already has, with their fields hidden):

- **Fields:** the share of fields the agent proposes that equal the true value, against the rule's. An agent that is no better here adds nothing.
- **Invented facts:** every claim in the description is traced to a field value or a tool result. A claim with no source (a weight, an ingredient, a
  health claim) counts as invented. The target is none.
- **Cost:** tokens and time per entry, from the stored conversation.

Whatever the result, it is reported as measured: a product-entry agent that does not beat the rule is documented as such, and the routine is labelled *Rule*.
Entries are stored as conversations (ADR 0054), so a partner can replay one without a key.

## Aito usage

The stock rule reads the Supply snapshot (Aito's discount sweep is in its overstock part). The agent's tools call `_predict` per field, as the
Product filling view does (`docs/aito-cheatsheet.md`); no new query shape.

## Acceptance criteria

- [ ] The Shopkeeper lists a stock run with steps for reorders and overstock, each with its outcome and the reason, under settings the page shows and lets a person move.
- [ ] With the defaults, the run's tally on the stored snapshot is the one above, and a test builds the run from the snapshot and compares it with the stored file.
- [ ] A reorder step above the limit is *Needs a person* whatever the evidence; a step with fewer observed sales than the bar is *Stay quiet*.
- [ ] No step orders anything; the run says it is simulated.
- [ ] (Agent, after the rule) a stored product-entry conversation with its tool calls, and a report of fields correct and invented facts against the rule, on held-out products.

## Demo impact

`docs/demo-script.md` 5b: the Shopkeeper shows two rules, win-back and stock, and a stored conversation; the agent joins it when it is built.

## Out of scope

Placing orders; a forecast; scheduling; the advertisement agent (its own ADR); changing Supply's lists.
