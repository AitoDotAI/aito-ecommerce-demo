# Demo script: the partner run (6–8 minutes)

One shop, its owner and an agent, all on one Aito database. Monday's run
goes from the owner's decisions to the shopper, then the agent, and closes
on the real-data evidence:

1. **Supply's headlines** (30 s): what to reorder, what is overstocked.
2. **Product what-if**: the decision for one product, before any lever.
3. **The lever** in a sandbox: 20 % or more off, and the decision pushes
   back to 10–15 %.
4. **The Shop** as Anna (shopper key `paivi`): her kit path, and the discounted hideout rising.
5. **The agent** reads the same sandbox and sees the offer just set.
6. **"How well?"** Evidence, ending on the real-data claim.

Each beat lists what to click, what to say, the number on screen and its
basis, the one caveat, and a recovery line. Every number was read on
2026-10-27 through the code paths named below, on `master`, which then held data
release 3a (ADR 0049, 0050). **Release 3b went live on 2026-10-29** (the data was
regenerated with churn tells and the action table, ADR 0051). Only section 1's
Supply numbers have been re-read since, from the release 3b snapshot; every other
number below is release 3a's and must be re-read before a partner demo (Product, the
Funnel and Pricing tabs, the Shop, the model checks), except the sections that say otherwise. The
sandbox template is loaded from release 2's files until it is reloaded, so a
sandbox run may differ from these (see "Open before a partner demo" at the end).
Numbers that need a sandbox are marked **(Sunday)** and carry no figure until
a sandbox run reads them: release 2's values for them are gone, not carried over. The
pre-flight is in the run sheet, `docs/notes/2026-10-26-ambientia-run-sheet.md`.

The app runs at **ecommerce.aito.ai**, or locally with `./do dev` at
`http://localhost:8500`. Before the cutover to release 2, run it locally
with `AITO_ENV=release2 ./do dev`. Sandbox mode needs the
sandbox database in the server's config (ADR 0043). Without it, the lever
and the agent don't run, and the banner doesn't show.

**Setup:** a screen 1440 px wide or wider. Open the first tab with
`?demo=1` (or start the server with `DEMO_MODE=1`): demo mode lasts for the
tab's session. It starts the Aito panel collapsed (the tab on the right
edge opens it), hides "Start free trial" and the Overview's year-on-year
growth, and folds each view's fine print behind **Details**, leaving one
plain caveat line. It changes no number: every basis is one click away.
Keep the sandbox link from the pre-flight in a second tab.

**Not on the path:** Patterns (it stays in "If there's time"), and
Retention. If Retention comes up (retention and loyalty are the Cartman storyline), lead with
who to reach, what they have been through and which action fits them (an email,
a discount, a voucher, an ad or an apology, each against doing nothing), not with
the euros: the actions and their outcomes are simulated and the page says so. Open the next
best action for one customer; say that an ad is only offered to customers who consented to
tracking, and that the model's top action is the generator's best for 81 % of customers
(`docs/verification/action-recovery.md`).

---

## Partner tour (platforms and agencies, about 6 minutes)

A different order from the owner's walk-through below: it starts from what a shopper sees and ends on how well it works.
Shop (Be Anna: what the shop suggests, and the query behind it) → Retention (who is about to leave, the ranked next action and what it adds) →
Shopkeeper (rules that act when the evidence is there, and the conversations of the agent that answers questions) → Analytics (tick conditions to build a segment, compare by profit per customer or NPS, drag a period on its trend to set it against the rest, see how they were acquired) →
Supply (reorder on observed sales; the markdown sweep is the Aito part) → Product (what a discount or price change does) →
Evidence (every number against a baseline, including the model that fails honestly). Every screen shows its query in the right panel.
Say once, early: all data is synthetic with planted effects; what is tested is whether Aito finds them.

## 1. Supply's headlines (30 seconds)

**Click:** the sidebar's **Supply** (or its card on the Overview).

**Say:** "Every morning the owner asks two things: what runs out, and what
is stuck on the shelf. The reorder list rests on what each product sold
lately, not on a forecast; Aito's estimates come in where they earn their
place, in how far a markdown moves the stock."

| On screen | Number | Basis |
|---|---|---|
| Reorder these 83 now | if May sells like the last three months, about €14,383 of its sales can't be served without them; 833 units, €12,620 at cost | each product's units a month over February to April (observed), against stock, the reorder point and safety stock (`src/supply_rows.py`); no forecast. Served from the precompute snapshot (`./do precompute`), which must be re-taken after a data release |
| €27,691 tied up in 79 overstocked products | say only the €27,691. Don't present the markdown split ("14 won't clear, none worth marking down") as a finding: it is the units model by price alone, which counts neither an offer's lift on purchases when shown (×1.79 at 20 %+) nor the higher place it earns in the shop, so it understates an offer and contradicts Product's "put it on offer" | the same `_estimate` at 5–20 % off, over 13 weeks; price only |

**Caveat (the page's one line):** the quantities assume May sells like the last
three months: observed sales, not a forecast. Aito's per-product forecast does not beat
last month's naive rule, which is why it sets no quantity here. **How well? →** opens the model checks.

**Check first:** the page shows 833 units. If it shows 664 units, or a "forecast" column, it is serving the snapshot
from before Supply moved to observed sales; if 730 units and €11,682, release 3a's: `./do precompute` has not been run
on master since the change or the data release.

**Recovery:** if Supply is slow on its first visit, the snapshot is
missing for this env; the Overview leaves its card out rather than wait.
Go on to the Product view.

## 2. Product what-if: the decision (about 1 minute)

### The sandbox

**Click:** **New sandbox** in the banner (it asks for the admin token
once per tab), or open the link made in the pre-flight. The URL gains
`?db=tmp-…`, and every view keeps it.

**Say:** "This is a branch of the whole store, made in milliseconds. What
I change here, the public shop never sees. It's thrown away in three
hours."

**Caveat:** the banner says it: a sandbox starts from the release data,
not from the live shop.

### The decision, before the lever

**Click:** go straight to
`/product/?sku=SKU-PT-0563&month=2026-05&tab=what-if&db=<branch>` (the
Trixie Hideout). Until a lever writes May, the view shows April.

| On screen | Number | Basis |
|---|---|---|
| The decision | "Put it on offer at 10–15 % off": bought when shown 12.9 % → 20.4 % (×1.58) | `_predict purchased` on `impressions` per discount band (`src/discount_what_if.py`); margin per showing (`src/product_decision.py`) |
| Margin per 100 showings | €129.80 → €147.94 (+14 %); break-even ×1.38 | list price €22.28, cost €12.25, one unit per purchase |
| Why | 14.0 % (all impressions) × 1.32 (10–15 % off, shop-wide) × 1.11 (this product's own) × 1.00 (Aito's normalising constant) = 20.4 % | the band's `$why`; at 10–15 % it was shown 8 times (0 bought), at 20 %+ 7 times (4 bought) |

**Presenter note, the Why row:** 0 of 8 is the observed count at 10–15 %; 20.4 % is the model's shop-wide lift.

## 2b. Pricing and the funnel (about 1 minute)

**Click:** `/product/?sku=SKU-PT-0194&month=2026-04` (PetNord Grain Free Daily Dental Treats 80g). The right side
opens on **Funnel**; **Pricing** is the tab beside it. In the editor, type `1.75` in **List price** (today €1.87).

**Say:** "Every property here moves the funnel. Showings narrow to clicks, clicks to purchases, and a purchase buys
one, two or three units, so the blocks are tallest first. The money is just the value."

| On screen | Number | Basis |
|---|---|---|
| Funnel today | 9.6 showings → 5.7 clicks → 4.0 purchases (3.2 × 1 unit, 0.6 × 2, 0.1 × 3) + 2.1 units re-ordered without a showing = 6.9 units; profit €6.44 | showings: `_estimate showings_index`; clicks and purchases: `_predict clicked`, and `purchased` given `clicked` (`src/product_funnel.py`) |
| At a list price of €1.75 | clicks 5.7 → 6.1, purchases 4.0 → 4.7, units 6.9 → 7.8, profit €6.44 → €6.32 | more shoppers, a thinner margin: the profit falls |
| Pricing tab | units 6.4 → 8.7 (+35 %); most profit among the prices it has data for: €1.59 list, €7.62 a month | `_estimate units_index` per price (`src/product_pricing.py`) |
| Cross-check | units by price 8.7, within 25 % of the funnel's 7.8 | the two routes are independent |

**Caveats to say out loud:** typing a price beyond what the product has sold at (€1.41–€1.90 paid) shows "no data
here", not a number. Advertising spend is our assumption (none, search €60, banner €180 a month), so a banner on a
€1.87 product loses money, which is the point of showing it. The click response to price is noisy across products;
the Pricing tab's curve is the cleaner view of price.

**Recovery:** if the funnel is slow on its first visit, the Aito slices are cold; reload once.

## 3. The lever: 20 % or more off, and the pushback (about 1½ minutes)

**Click:** on the left, in the product's form (in a sandbox it writes May 2026),
press **20 % or more off** under **Offer**. The KPIs on the right ask again;
each has a **?** that explains it. (Outside a sandbox the same buttons are a
preview and write nothing.)

**Say:** "The owner writes next month's state of this product. The app
reads it back from the database before it shows anything."

| On screen | Number | Basis |
|---|---|---|
| Read back | "May 2026, 20 % or more off, €17.27, 4 stars" **(Sunday)** | `src/product_levers.py`: April's list price €22.28 at the band's typical 22.5 %; April's stars are 4 (1 review) |
| The what-if's 20 %+ row | 22.3 % bought when shown, ×1.72 vs. no discount, band's lift 1.44 | the same `_predict`; shown 7 times at 20 %+ (4 bought) |
| The decision, May | "Change its offer to 10–15 % off": margin per 100 showings €111.97 (20 %+) → €147.94 (10–15 %) | the same band table with May's band as the current one; a sandbox run confirms it **(Sunday)** |
| Price model, May **(Sunday)** | units and profit at €17.27 and €19.50: read in the sandbox | `_estimate units_sold`, regression (`src/price_what_if.py`) |

**Say:** "The decision pushes back. At 20 % off it sells about as well as
at 10–15 % (22.3 % against 20.4 %), so the extra discount is margin given away. The owner gets the
estimate and the reason, and still decides."

**Click:** press **10–15 % off**: the owner takes the advice. The read-back
says "May 2026, 10–15 % off"; the decision should read "Keep its offer at
10–15 % off" **(Sunday)**.

| On screen | Number | Basis |
|---|---|---|
| The Shop's offer factor at 10–15 % **(Sunday)** | read in the sandbox: the card's score is Aito's probability × this factor | lift(10–15 %) / lift(none), each from the `$why` of `_predict purchased` (`src/shop_state_lifts.py`) |

**Caveat:** the offer's lift is shop-wide. Aito learned what a discount
does across all products, plus how this product sells. It hasn't learned
this product's own response to a discount.

## 4. The Shop as Anna (about 1½ minutes)

**Click:** **See the Shop react →**
(`/shop/?shopper=paivi&month=2026-05&db=<branch>`).

**Say:** "Anna got a guinea pig in February: a cage and a water bottle so
far. A shop sees what a visit is for, so it shows one view per intent."

### Her kit path

| On screen | Number | Basis |
|---|---|---|
| Next for their kit | PetNord Hideout 22 %, PetNord Exercise Wheel 18.4 %, Trixie Hideout, medium 18 %, Trixie Hideout, small 12.7 % | `_predict product_sku` on `order_lines` where `owned_before` holds a small-animal cage and water bottle (`src/shop_suggestions.py`); read on master for April; May's list in the sandbox **(Sunday)** |
| Buy again | PetNord Guinea Pig Mix Food 15kg, 67 % | `_predict skus.$feature` over her own orders before the month |

**Say, on the kit:** "Shoppers who owned a cage and a bottle bought a
hideout next: the PetNord Hideout leads, then PetNord Exercise Wheel and the Trixie hideouts. Aito reads that from
their order lines. The app has no kit rules."

**On variants:** in release 2 a product's variants carry their size in the
name ("Trixie Hideout, small" and "Trixie Hideout, medium"), so each shows as
its own card with its own number. Where two SKUs still share a name, a list
shows it once, as the SKU Aito ranked highest; scores are never added
(`src/same_name.py`).

### The discounted hideout rising

| On screen | Number | Basis |
|---|---|---|
| Before the lever | Trixie Hideout, small is already the 2nd card, "56 % buy it when shown" (April; May's rank **(Sunday)**). The rise after the lever is from 2nd, not from 10th: find the rank in the sandbox before telling it as a story | the Shop's measured `_recommend`, top 40, read on master |
| After **(Sunday)** | Trixie Hideout, small rises, with "Score … ↑ … since the offer" and the chip "On offer ×…, learned across the shop" | `src/shop_rescore.py`: Aito's probability × the offer band's factor; the rank change counts cards, as the page shows them |
| The card's explanation | "Aito's purchase probability … × offer band lift (shop-wide) × star band lift (shop-wide) = score …" | offer factor = lift(band) / lift(none), each from `$why` of `_predict purchased` (`src/shop_state_lifts.py`) |

**Point at the Aito panel** (open it with the tab on the right edge):
"The query holds only what a shop knows: the pets she told us, the month
and her cart."

**Say:** "The hideout rises, and the card says why: the
explanation multiplies out to the number shown. The probability is Aito's,
and so is the offer's lift. Multiplying them is this app's choice, and the panel
says so."

**Caveat (the page's one line):** the re-scored card shows a score, not a
rate. The rest (the top 40, the multiplication) is behind **Details**. The
re-scored Shop exists only in the sandbox.

### Optional: a 1-star review

**Optional. Click:** back on the product, add a 1-star review with any text.

| On screen | Number | Basis |
|---|---|---|
| Read back **(Sunday)** | the star band before and after, with the review count and average | April: Trixie Hideout, small is in the 4-star band with 1 review; `rating_band` uses the generator's rule (`data/shoppers.py`) |
| Shop card **(Sunday)** | a chip "… stars ×…, learned across the shop" and the new score | lift(new stars) / lift(April's stars), from `$why` (`src/shop_state_lifts.py`) |

**The honest case, to pick on Sunday:** release 3b's products carry few
reviews (the Trixie Hideout, small has 1), so one review often moves the band. The
"no change" example (a 5-star review on a product with many 1–2 star ones,
read back as "No change in its star band") needs a product with many
reviews; find one in the sandbox and write it here. **Say:** "One good
review doesn't undo many bad ones, and the view doesn't pretend it does."

**Recovery:** if a lever answers 400, the sandbox has expired or belongs
to another server: press **Reset: new sandbox**, or open the spare link.
If the Shop doesn't move, check that the URL still has `?db=` and
`month=2026-05`.

**Without a sandbox:** the public Shop, `/shop/?shopper=paivi`, is April
2026 and shows the same kit path and Buy again. Its "Picked for you" leads
with Trixie Hideout, medium, "58 % buy it when shown", ★ 5, no offer
(`_recommend impressions` with her pets read from her orders, the month and the cart,
`src/shop_ranking.py`). Press the **?** on a card for the `$why` chain behind its
percentage. Her Buy again rests on a single earlier order, so 67 % comes from
very little history.

**Recovery:** if the grid stays empty, the backend can't reach its data
release (`/api/health`, `data_release.state`). Switch to the static
screenshots.

## 5. The agent (about 1½ minutes)

**Click:** a terminal: `./do agent-demo <branch>`, the same branch as the
browser's (setup and rehearsal: the run sheet).

**Ask:** "What has the owner set for May, and what would an offer do for
those products?"

**Say:** "This is a merchant's agent: Claude, with Aito's MCP server as
its only tools. It has a read-only key to this sandbox, and it may only
propose."

| Expected | Basis |
|---|---|
| It finds the Trixie Hideout's May row: 20 % or more off, €17.27 **(Sunday)** | `search product_states where {month: 2026-05}` |
| It quotes 12.9 % at no discount and 22.3 % at 20 %+, calls the lift shop-wide, and calls the 7 showings at 20 %+ thin (as April reads on master; the sandbox's May may differ) **(Sunday)** | the same `_predict purchased` per band the Product view sends |

**Caveat:** the agent's judgement varies from run to run on the same data.
It proposes, and a person decides. Its brief tells it to quote only
numbers a tool returned.

**Recovery:** if a tool call fails or stalls, play `agentic-demo.mp4` from
the deck folder (68 s, two real runs on the same data, recorded
2026-10-24).

## 5b. The shopkeeper: rules and agents (about 2 minutes)

**Click:** Operate › Shopkeeper. The Weekly win-back run is open.

**Say:** "These are the shop's routines, each marked Rule or Agent. The win-back
is a rule: a calculation on Aito's numbers, no model in it. It went through the
20 customers most likely to leave and picked the next best action for each, and
acts only when the evidence is there. Everything here is simulated: nothing was sent."

| Expected | Basis |
|---|---|
| "I acted on 4, expecting € 67 more than doing nothing. 5 are waiting for you, holding € 48 expected. I stayed quiet on 11." | the stored run `data/agent_runs/winback.json` at the recommended settings; the euros are expected values from Aito's predictions |
| A "stayed quiet" step names why: for example "Only 9 past rows match this customer's exact situation and €10 voucher; the rule asks for 10" | rows of that action in that situation in `customer_actions` (a check on the evidence, not what the lift is estimated from) |
| Moving "Act from a lift of" up turns acted steps into suggested ones; unticking a kind under "Always ask a person before" moves its steps out of "Needs a person", to Acted or Suggested by their lift | the gate's rules, re-judged on every change |
| The Board lists what to improve: thin evidence, the approval load, and the churn tells (NPS 0–3: 1.9× the churn) | the Retention snapshot's `_relate` rates |

**Say:** "The store sets how sure the rule must be, and which kinds always
need a person. We don't claim it matches or forecasts better than a simpler
method: the gate is what's new, it knows when not to act."

**Then:** open "Stock-aware morning check" under Runs: a second rule, over what Supply serves. Of 98 products it orders 40 (€4,991), leaves 9 for a person and 49 quiet; move "Units sold, at least" or the order limit and the outcomes move. It orders nothing and says it is a rule on observed sales.

**Then:** open a stored conversation under Past conversations (when one is stored: `./do record-conversations`
stores one from a server where Ask is on). It shows the question, each tool call with its input and result, the
answer and the tokens: this is where a model works, read-only, and it replays without a key.

**Caveat:** only the win-back routine is built; the others are shown as not built
yet. The numbers are those of the stored run for the current data release; a run
stored for another release shows a "stale" notice.

## 6. How well? Evidence: the close (about 1 minute)

**Click:** the sidebar's **Evidence**, then **Business reorders** (Real
data).

**Say, word for word:** "For buyers with 1–2 earlier orders, Aito's top
suggestion was in their next orders 31 % of the time, against 15 % for
the strongest of five classical baselines."

| Number | Basis |
|---|---|
| 31 %: 197 of 636 buyers, 95 % [27.4, 34.6] | Aito core's pre-registered benchmark (aito-core 625867faca), reproduced by `./do uci-check` (`tests/test_aito_check.py`) |
| 15 %: EASE, 15.4 % [12.6, 18.2] | the same benchmark (ADR 0034, ADR 0036) |

**Say also:** "It's the top suggestion, not the whole order. For regular
buyers, with 3 or more orders, Aito ties the best simple method. With no
history, it equals popularity. The data is a UK giftware wholesaler's:
public, CC BY 4.0."

In demo mode the page keeps its method and intervals in view; only the
longer interpretation notes fold behind **Details**.

**On screen, don't dwell on:** the page's default buyer (12357) ordered
131 products next, so a hit is easy for this buyer; the 31 % is the
measure. Aito's 0.3–0.4 % per product is a probability among 4,415
products, not a confidence in the order.

**The caveat to say aloud:** "Everything on the PetNord screens is
generated data with planted effects. It shows how Aito works, not how much
it would lift your shop. The real-data number is the one on this page."

**Optional, synthetic:** on months it hadn't seen, Aito's purchase
estimate per discount band came within 6 % of what shoppers then did
(`docs/aito-cheatsheet.md`, "A discount band as a what-if": Jan–Apr 2026
held out, 56,005 impressions). That was measured on release 2 data and has not been re-run on release 3b.

## Close (20 seconds)

> "One shop, five owner views, two back-office tools and an agent, all on
> one Aito database. No model training, no retraining schedule. The query
> in the panel is the call your frontend would make, and the source is on
> GitHub."

---

## If there's time

- **Patterns** stays out of the path; use it only if asked about baskets.

- **Patterns** (`/patterns/?anchor=dog_dryfood`): dog dry food and dental
  treats are in the same basket 3.17× more often than chance (interval
  2.75–3.66). 64 % of dog dry-food orders have dental treats, and 96 %
  the other way round (2,044 of 10,594 orders hold both). Source: `/api/shop-analytics/baskets`.
- **What goes with a purchase** (Patterns): products on offer are 1.41×
  over-represented in purchases ([1.29, 1.53], 2,518 of 6,069 rows). Say "on
  generated data with a planted offer effect". Don't set it beside the
  planted ×2.5: one is a share ratio, the other an odds ratio.
- **Shop search:** switch to Janne and search "food": only grain-free
  food, his household's rule.
- **Product filling:** five fields predicted from a product's name and
  brand, each with its `$why`.

## Quick recovery

| Symptom | Recovery |
|---|---|
| Any view answers 400 with `?db=` | The sandbox expired (3 h) or isn't on this server. **Reset: new sandbox**, or the spare link. |
| The first click after a pause takes about 5 s | DNS: the app keeps connections for 5 minutes, and this laptop's lookups can take 5 s. The run sheet has the hosts pin. |
| The May Shop says "open a sandbox" | The URL lost `?db=`. Use the Product view's link back. |
| The lever's read-back fails | Don't retry on stage: **Reset: new sandbox**, then pull again. |
| The agent stalls | Play `agentic-demo.mp4`. |
| Everything is slow | Switch to the deck's static screenshots (the run sheet's "Fallbacks"). |

## Common questions

**"Is this real data?"** PetNord is generated, with planted effects, to
show the mechanics. The Evidence section marks each page Real or
Synthetic, and the real-data claim is on UCI Online Retail II.

**"Does Aito learn the shopper's history?"** The Shop's query holds what
she declared (her pets), the month and the cart, and Aito learns from
every shopper's rows. Putting her id in the query measured no better
(ADR 0033's amendment), so the Shop leaves it out.

**"What does a lever write?"** One `product_states` row for next month
(and, for a review, one `reviews` row), through Aito's `_modify`, in a
sandbox branch only. PetNord's database is read with a read-only key, and
the code refuses any write to it (ADR 0043).

**"How would my shop's data get in?"** As tables like these, through the
same loader. The schema is in `src/schema.py`.

## Open before a partner demo

- **Take the precompute snapshots on master** (`./do precompute`): Overview, Supply, Retention and Demand are served
  from snapshots. After the release 3a promote, prod still served release 2's (Supply showed 676 units and €11,097
  where master computes 730 and €11,682). A release's switch script should run this before the promote
  (`AITO_ENV=<release env> ./do precompute --as master`), so the snapshots travel with the data.
- **The sandbox run (Sunday items):** the lever's read-back, the Shop's rank before and after, the offer factor, the
  agent's quotes. The sandbox template must be reloaded from release 3a first (`./do sandbox-template-load`); until
  then a sandbox holds release 2's data and its numbers will not match this script.
- **The rising hideout:** the Hideout is already the 3rd card before the lever. If it rises from 3rd to 1st, say
  that; if the sandbox shows no rise, pick another product for the story.
- Sections 6 (UCI, real data) and the "Optional, synthetic" held-out figure (6 %, Jan–Apr 2026) were not re-read: the
  UCI numbers do not depend on release 3a, and the held-out figure needs `docs/aito-cheatsheet.md`'s measurement
  re-run on release 3a.
