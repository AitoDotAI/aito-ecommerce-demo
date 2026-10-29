# Does Aito recover the planted best action? (ADR 0051, slice 1)

Run on env `release3b`, 2026-10-29, 300 random customers from `action_contexts`;
`docs/verification/action_recovery_probe.py` reproduces it. The data is simulated:
five situations were planted (`data/customer_actions.py`, A1–A5) and the shop's
assignment of actions is partly random. The question is whether Aito's
`_predict`s, read back as Retention reads them, point at the action the generator
makes best, not whether the actions work in a real shop.

| Policy | Mean regret per customer (generator's expected net, €) |
|:--|--:|
| Aito's ranking (top action) | 3.03 |
| Always email | 9.29 |
| Never act | 10.44 |

Aito's top action is the generator's best in 48 % of customers (seven candidates; a
first run, before apologies and ads were given to more contexts, gave 54 %). The
regret is a third of the best single action's.

What it takes, found by running it:
- **Cross the action with each context column.** Without `action_x_<context>` columns
  the picks were wrong in the obvious way: an apology and an ad lifted orders for
  customers with no issue and no tracking consent, because Aito adds evidence
  column by column and an action's average effect leaked into every context.
- **Keep an action's parameter columns its own.** An apology's €5 credit was first stored as
  `voucher_eur = 5`, and the evidence of the apologies (given to unhappy customers) read as
  evidence for €5 vouchers.
- **The assignment must vary.** An action only ever given where it works cannot show where it does not.

Caveats: the margin between two actions is a difference of two small estimates, so
runner-up picks are noisy (it over-picks the ad and the apology); the sample is one seed
of one generation; the generator's net uses the customer's spend band's order value from
`_estimate`, as the app does.
