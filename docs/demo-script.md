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
2026-10-25 through the code paths named below, on env `release2`, which
holds data release 2 (ADR 0045, amendment 2). The sandbox template is loaded
from the same release files, so its numbers should match. Numbers that need a
sandbox are marked **(Sunday)** and carry no figure until Antti's sandbox run
reads them: release 1's values for them are gone, not carried over. The
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
Retention. If Retention comes up, lead with who to reach and why, not with
the €135 the win-back emails return: that is a small, synthetic sum.

---

## 1. Supply's headlines (30 seconds)

**Click:** the sidebar's **Supply** (or its card on the Overview).

**Say:** "Every morning the owner asks two things: what runs out, and what
is stuck on the shelf. Aito forecasts next month's sales per product; the
euros follow from that forecast."

| On screen | Number | Basis |
|---|---|---|
| Reorder these 83 now | an estimated €11,097 of May's sales can't be served without them; 676 units, €10,659 at cost | `_estimate units_sold` per SKU for May 2026, against stock and the reorder point (`src/supply_rows.py`); served from `data/precomputed/v2-master/supply.json` |
| €28,298 tied up in 79 overstocked products | say only the €28,298. Don't present the markdown split ("14 won't clear, none worth marking down") as a finding: it is the units model by price alone, which counts neither an offer's lift on purchases when shown (×1.79 at 20 %+) nor the higher place it earns in the shop, so it understates an offer and contradicts Product's "put it on offer" | the same `_estimate` at 5–20 % off, over 13 weeks; price only |

**Caveat (the page's one line):** the forecasts are Aito's estimates for
May; the euros follow from them. **How well? →** opens the model checks.

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
| The decision | "Put it on offer at 10–15 % off": bought when shown 20.6 % → 37.1 % (×1.80) | `_predict purchased` on `impressions` per discount band (`src/discount_what_if.py`); margin per showing (`src/product_decision.py`) |
| Margin per 100 showings | €206.67 → €269.17 (+30 %); break-even ×1.38 | list price €22.28, cost €12.25, one unit per purchase |
| Why | 14.2 % (all impressions) × 1.59 (10–15 % off, shop-wide) × 1.73 (this product's own) × 0.95 (Aito's normalising constant) = 37.1 % | the band's `$why`; at 10–15 % it was shown 6 times, at 20 %+ twice |

## 3. The lever: 20 % or more off, and the pushback (about 1½ minutes)

**Click:** on the left, in the product's form (in a sandbox it writes May 2026),
press **20 % or more off** under **Offer**. The KPIs on the right ask again;
each has a **?** that explains it. (Outside a sandbox the same buttons are a
preview and write nothing.)

**Say:** "The owner writes next month's state of this product. The app
reads it back from the database before it shows anything."

| On screen | Number | Basis |
|---|---|---|
| Read back | "May 2026, 20 % or more off, €17.27, 3 stars" **(Sunday)** | `src/product_levers.py`: April's list price €22.28 at the band's typical 22.5 %; April's stars are 3 (2 reviews) |
| The what-if's 20 %+ row | 40.8 % bought when shown, ×1.98 vs. no discount, band's lift 1.79 | the same `_predict`; it was shown twice at 20 %+, so the band's lift is the shop-wide one |
| The decision, May **(Sunday)** | "Change its offer to 10–15 % off": margin per 100 showings €204.84 (20 %+) → €269.17 (10–15 %) | the same estimates, with May's band as the current one |
| Price model, May **(Sunday)** | units and profit at €17.27 and €19.50: read in the sandbox | `_estimate units_sold`, regression (`src/price_what_if.py`) |

**Say:** "The decision pushes back. At 20 % off it sells about as well as
at 10–15 %, so the extra discount is margin given away. The owner gets the
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
| Next for their kit | Trixie Hideout, small 25 %, Trixie Hideout, medium 16 %, PetNord Hideout 14 %, Trixie Exercise Wheel 13 % | `_predict product_sku` on `order_lines` where `owned_before` holds a small-animal cage and water bottle (`src/shop_suggestions.py`); read on `release2` for April; May's list in the sandbox **(Sunday)** |
| Buy again | PetNord Guinea Pig Mix Food 15kg, 67 % | `_predict skus.$feature` over her own orders before the month |

**Say, on the kit:** "Shoppers who owned a cage and a bottle bought a
hideout next. Aito reads that from their order lines. The app has no kit
rules."

**On variants:** in release 2 a product's variants carry their size in the
name ("Trixie Hideout, small" and "Trixie Hideout, medium"), so each shows as
its own card with its own number. Where two SKUs still share a name, a list
shows it once, as the SKU Aito ranked highest; scores are never added
(`src/same_name.py`).

### The discounted hideout rising

| On screen | Number | Basis |
|---|---|---|
| Before the lever | Trixie Hideout, small is the 10th card, "36 % buy it when shown" (April; May's rank **(Sunday)**) | the Shop's measured `_recommend`, top 40, read on `release2` |
| After **(Sunday)** | Trixie Hideout, small rises, with "Score … ↑ … since the offer" and the chip "On offer ×…, learned across the shop" | `src/shop_rescore.py`: Aito's probability × the offer band's factor; the rank change counts cards, as the page shows them |
| The card's explanation | "Aito's purchase probability … × offer band lift (shop-wide) × star band lift (shop-wide) = score …" | offer factor = lift(band) / lift(none), each from `$why` of `_predict purchased` (`src/shop_state_lifts.py`) |

**Point at the Aito panel** (open it with the tab on the right edge):
"The query holds only what a shop knows: the pets she told us, the month
and her cart."

**Say:** "The hideout rises to first, and the card says why: the
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
| Read back **(Sunday)** | the star band before and after, with the review count and average | April: Trixie Hideout, small is in the 3-star band with 2 reviews; `rating_band` uses the generator's rule (`data/shoppers.py`) |
| Shop card **(Sunday)** | a chip "… stars ×…, learned across the shop" and the new score | lift(new stars) / lift(April's stars), from `$why` (`src/shop_state_lifts.py`) |

**The honest case, to pick on Sunday:** release 2's products carry few
reviews (the hideouts have 2), so one review often moves the band. The
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
with PetNord Fruit Drops Treats 100g, crunchy, "56 % buy it when shown", ★ 4.3, −18 % this month
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
| It quotes 10.6 % at no discount and 19.7 % at 20 %+, calls the lift shop-wide, and calls 5 showings at 20 %+ thin **(Sunday)** | the same `_predict purchased` per band the Product view sends |

**Caveat:** the agent's judgement varies from run to run on the same data.
It proposes, and a person decides. Its brief tells it to quote only
numbers a tool returned.

**Recovery:** if a tool call fails or stalls, play `agentic-demo.mp4` from
the deck folder (68 s, two real runs on the same data, recorded
2026-10-24).

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
held out, 56,005 impressions).

## Close (20 seconds)

> "One shop, five owner views, two back-office tools and an agent, all on
> one Aito database. No model training, no retraining schedule. The query
> in the panel is the call your frontend would make, and the source is on
> GitHub."

---

## If there's time

- **Patterns** stays out of the path; use it only if asked about baskets.

- **Patterns** (`/patterns/?anchor=dog_dryfood`): dog dry food and dental
  treats are in the same basket 2.66× more often than chance (interval
  2.34–3.03). 67 % of dog dry-food orders have dental treats, and 97 %
  the other way round. Source: `/api/shop-analytics/baskets`.
- **What goes with a purchase** (Patterns): products on offer are 1.60×
  over-represented in purchases ([1.49, 1.72], 3,998 rows). Say "on
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
