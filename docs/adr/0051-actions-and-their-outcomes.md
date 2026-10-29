# ADR 0051: Actions and their outcomes — retention, advertising, availability and customer messages

**Status:** Slice 1 accepted and live (2026-10-29, data release 3b: `customer_actions`, `action_contexts`, Retention's ranked actions). The messages, employees and availability parts are still proposed. Antti: retention and loyalty should cover a wider range of actions
(personalized discounts, vouchers or compensation, messages tied to something the customer did, personalized
advertising); availability is an action for the shop ("something out of stock but orderable with a wait time");
"an action table with one or more context, action, parameter(s) and KPI … the data should stage a situation where an
action was, or was not, taken, and then measure the activation of the user over a period of time"; and fully connected
feedback and NPS data, with message classes and routing to employees as in `aito-demo`.
**Date:** 2026-10-28
**Build:** in slices. Slice 1 (Retention's ranked actions, `customer_actions`, `action_contexts`) is on its branch; messages, availability and the unified score follow, each with its own PR.
**Deciders:** Antti
**Builds on:** ADR 0020 (win-back offer), ADR 0027 (staple category), ADR 0038 (product state), ADR 0049/0050 (release 3a)

## Context

Retention picks one action for an at-risk customer: a product email, chosen by expected return
(chance of an order × order value − the email's cost, `src/winback_offer.py`). The same decision applies to every
lever a web shop has, and the comparison across levers is what a shop owner needs: is a €5 voucher worth more
than a €0.50 email for this customer, this month?

Three things are missing.

**One action, learned from one table.** `winback_campaigns` records only product emails, and only whether the
customer ordered. A discount, a voucher, a back-in-stock note or an ad has no row anywhere, so nothing can be
compared with it. Neither is there a row for "no action", so an email's effect cannot be told from the customers
who would have ordered anyway. Discounts and vouchers cost margin, so the effect, not the response, is what is
worth paying for.

**Outcomes are one yes/no.** A customer who was nudged may visit, click, order, or rate the shop. The chain
visit → click → purchase has a different probability at each step, and the action may move one step without
moving the next (an ad lifts clicks but not orders).

**Availability is a state with no action.** A product that is out of stock but can be ordered with a wait is sold
at a lower click and purchase rate. The shopkeeper can order it. Today `product_states.stock` has `in_stock | low`
only, and nothing in the product view lets an owner act on it.

**Customer messages are not connected to customers.** `aito-demo` classifies a message as `question`, `feedback`
or `request` with one `_predict type`, predicts sentiment and category for feedback, and predicts the assignee
(an `employees` row) and urgency for a request. Those messages do not belong to a customer, so a complaint cannot
inform a retention action, and NPS cannot be an outcome.

## Decision

### Data (release 3b, a new env, generated like release 3a: seeded, simulated, labelled)

1. **`customer_actions`** — one row per action instance, including "no action":
   - `action_id`, `customer_id` (link), `month`;
   - context, as the customer was when the action was chosen: `recency_bucket`, `risk_band`, `staple_category`,
     `open_message_category` (nullable, from `customer_messages`), `spend_band`;
   - `action` (`none | email | discount | voucher | ad | back_in_stock | apology`) and its parameters:
     `product_sku` (nullable), `discount_pct` (a band, `"0" | "5" | "10" | "15"`; a band because decimals only
     match equal cents, release 3a finding), `voucher_eur` (a band), `cost_eur`;
   - outcomes within 7 and 30 days: `visited_7d`, `clicked_7d`, `purchased_7d`, `visited_30d`, `clicked_30d`,
     `purchased_30d`, `spend_30d_eur`, `nps` (nullable: only some customers answer).
   - Assignment is partly random and partly rule-driven in the generator, so "none" exists in every context. The
     generator's assumed lifts are written into the preregistration, and the UI labels these rows as simulated.
2. **`customer_messages`** — `message_id`, `customer_id` (link), `month`, `message` (Text), `type`
   (`question | feedback | request`), `sentiment`, `category`, `urgency`, `assignee` (link `employees.name`),
   `resolved_days` (nullable). Messages link to the customer, so a complaint becomes a context for an action.
3. **`employees`** — name, role, department, superior (from `aito-demo`, trimmed to the shop's roles).
4. **`product_states.stock`** gains `sold_out_orderable` (an order wait of `wait_days` is shown), and
   `monthly_sales` gains the showings and sales during that state, so the drop in click and purchase rates is
   learned from the data and not assumed in the app.

### Aito usage

- **Which action:** per customer and candidate action, `_predict` on `customer_actions` with the context and the
  action in the `where`, for each outcome (`visited_30d`, `clicked_30d`, `purchased_30d`). The candidates come from
  the generator's action vocabulary plus `none`.
- **Value of an action** is the difference to `none` in the same context, not its raw rate:
  `uplift = p(purchased | context, action) − p(purchased | context, none)`. Expected net return is
  `uplift × order value (_estimate spend_30d_eur given purchased) − cost_eur`.
- **One scale, as Antti suggested:** the score of an action is P(visit)·P(purchase | visit) + P(click)·P(purchase | click),
  with each conditional asked as `_predict purchased_30d` with `visited_30d: true` / `clicked_30d: true` in the
  `where` (the pattern the release 3a funnel uses for conversion). The view can also rank by P(visit) alone.
  The two are shown side by side so a reader sees when the ranking changes.
- **Message routing:** `_predict type` on `customer_messages.message` (a Text column), then sentiment, category or
  assignee and urgency by type, as in `aito-demo`. Uncertain messages (top `$p` under a threshold) are shown as
  "needs a person"; in a production system they would go to the sender, to a Decision API, or through vector
  search for semantics. The demo shows the hand-off and does not build those.
- **Availability:** the Pricing/Funnel machinery asks the click and conversion rates at `stock: sold_out_orderable`
  and at `in_stock`; the lost units are the difference, and the shopkeeper's "order it" action is a state edit like
  the list price (ADR 0050).
- A never-seen action or context value returns the base rate with a 200 (release 3a finding): the service
  validates against the known vocabulary and fails loudly.

### Views

- **Retention** — an at-risk row lists the ranked actions (action, parameter, expected net euros, the visit /
  click / purchase chances) instead of one email. The action table's dated rows are shown for a customer as
  "what we did and what happened".
- **Product** — a stock state with an "order it" action; the Funnel shows the lost units.
- **Messages** — a small view: a message is classified, shown with its sentiment and category, routed to an
  employee, and joined to the customer's open actions.
- **Overview** — action outcomes over time as the KPI the actions are optimized for.

### Slice 1, as built

- `customer_actions` has the context as six bands (`recency_bucket`, `spend_band`, `offer_buyer`, `open_issue`,
  `email_history`, `tracking_consent`), the action with its parameter bands, and `visited_30d`, `clicked_30d`,
  `purchased_7d`, `purchased_30d`, `spend_30d_eur`, `cost_eur`, `net_30d_eur`. `nps` and `open_message_category` wait for
  `customer_messages`: `open_issue` (a late delivery, a detractor answer) stands in for the open complaint until then.
- `action_contexts` holds each customer's context as of the next month, derived by the same code as the training rows, so the
  app does not re-derive it.
- The planted situations are written down in `data/customer_actions.py` (A1–A5, each with a switch in
  `data/planted_switches.py`): an email works on those who answered one; a discount on those who buy on offer; a voucher
  on the lapsed; an ad on those who consented to tracking; an apology on an open issue.
- The net is `(P(order | action) − P(order | none)) × order value − cost`; the cost arithmetic is the shop's own
  (`src/retention_actions.py`), Aito supplies the chances and the order value.

## Acceptance criteria

- [ ] A retention row shows at least three candidate actions with an expected net return each, and "no action" as
      the baseline the uplift is taken against.
- [ ] The ranking can be switched between purchase-weighted score and P(visit); the order changes for at least
      one customer in the demo data, and the page says why.
- [ ] A discount or voucher that has no uplift for a customer shows a negative or zero net return, not a gain.
- [ ] A customer with an open complaint has it as part of the context, and the recommended action changes with it.
- [ ] A product marked sold out but orderable shows lower click and purchase rates and the units lost, and the
      "order it" action moves them back.
- [ ] A typed message is classified (question / feedback / request), and a request is routed to an employee; a
      low-confidence message is shown as needing a person.
- [ ] Simulated rows are labelled as such in the UI and the preregistration.
- [ ] `aito-check` asserts the structure and probability bounds of each new query, and the sold-out drop.

## Demo impact

Retention becomes "the best action of several", which is the Cartman storyline (retention, loyalty, personalized
advertising). The consultancy story (Ambientia, tailorability) gains a concrete table: add your own actions and
outcomes as rows, and the ranking follows. `docs/demo-script.md` gains one moment: pick an at-risk customer, see
the ranked actions, take one in the sandbox and see the outcome row.

## Out of scope

- Sending real messages, vouchers or ads; the demo records an action, it does not execute it.
- Measured uplift: no real experiment data exists. The generator's lifts are assumptions, stated and labelled.
- A message-routing model quality study; low-confidence hand-off is shown, not built (Decision API, vector search).
- Attribution across several overlapping actions in the same month (one action per customer per month here).

## Consequences

- A new release (3b) with its own preregistration, env, and `data/release-env.json` change, so the data-release
  gate (ADR 0035) and the switch procedure apply.
- The action vocabulary is closed in the generator; a consultancy adding an action adds rows and a vocabulary
  entry, which `check_changes`-style validation then accepts.
