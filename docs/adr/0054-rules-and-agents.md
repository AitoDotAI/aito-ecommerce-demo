# ADR 0054: Rules and agents: what the shop decides by calculation, and what a model does

**Status:** Accepted (2026-11-01, Antti: "Sounds good" to the split, stored conversations and the plan). Slice 1 built (labels, stored conversations, `./do record-conversations`); no conversation is stored yet: recording one costs a model run and needs the admin token, so it is Antti's to run.
**Supersedes in part:** ADR 0052 (the routines are not all "agents"; "Past conversations" meant stored runs).
**Date:** 2026-11-01
**Deciders:** Antti

## Context

The Shopkeeper view calls everything an agent. Looking at the code, the win-back list is a calculation:
`build_winback_run` is deterministic over the Retention snapshot, and the gate (act, suggest, stay quiet,
never auto) is a rule on Aito's lift and on the number of matching past rows. No model writes or ranks
anything in it. The only place a language model works is "Ask the store" (ADR 0042), and its answers are
not kept, so nobody can read an earlier conversation or test one without a key.

Calling a calculation an agent overclaims, and it hides the places where a model would earn its cost.
When the calculation is good enough, an agent adds nothing but cost and variance.

## Decision

1. **Every routine and decision is labelled one of two things, and the page says which.**
   - **Rule** (algorithmic): decided by Aito queries and arithmetic on stored facts. Repeatable: the same data gives the same answer. Today: win-back actions and the gate, the reorder and overstock lists, the discount what-if, the Retention drivers.
   - **Agent** (a model works): a model reads, writes or orchestrates, with tools and a person's approval. Planned: filling and improving product text and fields, advertisement orchestration, inventory orchestration. Today: "Ask the store" only.
2. **Rules are not described in agent words.** No "the agent acts" for a rule; "the rule acts" or "the shop's gate acts".
3. **Agent conversations are stored and shown.** A conversation holds the question, each tool call with its input, result, duration and error, the answer, the model, tokens and the data release. "Past conversations" lists these, not runs. Win-back runs move to a list called "Runs".
4. **Conversations can be tested without a key.** Stored conversations replay in the page. Asking a new question stays behind the presenter's admin token (it costs money and calls an outside service), and `./do record-conversations` stores the predefined questions that have no conversation yet (keys from the dotenv file) as files in `data/ask_conversations/`.
5. **The next agent routines** are chosen where an agent is the better tool than a rule: product text that has to be written, and multi-step orchestration across advertisement and stock. Each gets its own ADR with an evaluation against the rule that would do it without a model.

## Aito usage

Unchanged. The agent's tools wrap the app's existing services (Product what-if, Supply, Retention), read-only.

## Acceptance criteria

- [ ] Every routine on the Shopkeeper view carries a "Rule" or "Agent" label, with a line saying why.
- [ ] "Past conversations" lists stored question-and-answer conversations; stored runs are listed as "Runs".
- [ ] A user can open a stored conversation and see the question, every tool call (input, result, duration), the answer, model and token counts, with no API key.
- [ ] With no stored conversation the list says so and names the command that records one.
- [ ] `./do record-conversations` stores each predefined question that has no conversation yet, and a test covers which are missing.

## Demo impact

`docs/demo-script.md`: the Shopkeeper section says "rule" for the win-back list, and shows a stored conversation.

## Out of scope

Scheduled live runs, writing back to the shop, new agent routines (each its own ADR), and a server-side log of
visitors' questions.
