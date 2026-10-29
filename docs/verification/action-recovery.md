# Does Aito recover the planted best action? (ADR 0051, slice 1)

Run on env `release3b`, 2026-10-29, 300 random customers from `action_contexts`;
`docs/verification/action_recovery_probe.py` reproduces it. The data is simulated:
five situations were planted (`data/customer_actions.py`, A1–A5) and the shop's
assignment of actions is partly random. The question is whether Aito's
`_predict`s, read back as Retention reads them, point at the action the generator
makes best, not whether the actions work in a real shop.

| Policy | Mean regret per customer (generator's expected net, €) |
|:--|--:|
| Aito's ranking (top action) | 0.45 |
| Always email | 9.36 |
| Never act | 10.72 |

Aito's top action is the generator's best in 81 % of customers (seven candidates), and its regret
is a twentieth of the best single action's (on the data with the churn tells, ADR 0039's amendment; 72 % and €0.97 before it). Earlier runs on the way: 54 % and €2.93 with the crossed columns
and a shop that rarely tried an action where it does nothing; 48 % and €3.03 with a little more variety.

What it takes, found by running it:
- **Cross the action with each context column.** Without `action_x_<context>` columns
  the picks were wrong in the obvious way: an apology and an ad lifted orders for
  customers with no issue and no tracking consent, because Aito adds evidence
  column by column and an action's average effect leaked into every context.
- **Keep an action's parameter columns its own.** An apology's €5 credit was first stored as
  `voucher_eur = 5`, and the evidence of the apologies (given to unhappy customers) read as
  evidence for €5 vouchers.
- **The assignment must vary.** An action only ever given where it works cannot show where it does not. Half of the generated
  assignments are a randomised test, half follow the shop's rules; with the rules alone, 48 %.
- **Some of it is a rule, not a model.** Even so, Aito put a personalised ad a few points above no action for customers who
  declined tracking, where the data shows none (`probe_where`: 0.196 vs 0.144). An ad needs consent, so Retention does not offer
  one to them (`candidates_for`). The same bias, "any action beats none", shows smaller on the others.

Caveats: the margin between two actions is a difference of two small estimates, so
runner-up picks are noisy (it over-picks the ad); the sample is one seed
of one generation; the generator's net uses the customer's spend band's order value from
`_estimate`, as the app does.
