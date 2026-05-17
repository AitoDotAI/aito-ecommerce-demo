# Demo script — the two-minute PetNord walkthrough

A narrated path through PetNord that hits every demo moment in
`TASK.md` order. Aim for two minutes; ninety seconds is better.
Every beat names the page, the click, the expected Aito panel
state, and the quote the sales engineer says.

The demo runs at **ecommerce.aito.ai** (or `./do dev`
locally → `http://localhost:8500`).

---

## Setup

- Open the running app to `/` (Dashboard).
- Make sure the Aito panel is open on the right (lightning toggle
  in the topbar opens it if it isn't).
- Screen at 1440 px or wider — the side-by-side moments need
  both panels visible without scrolling.

---

## Beat 1 — Dashboard (15 s)

> "PetNord is a Nordic pet store. 11 970 orders, 658 SKUs, 3 000
> customers — twenty-four months of data, all live in Aito. The
> top-pattern row says dog dry-food and dental treats co-occur
> at 2.68× baseline — that's `_relate`, with no model training."

Aito panel: `_relate` endpoint badge teal. Query body shows the
`from: orders, where: {line_categories: {$match: dog_dryfood}}`
shape. The 2.68× number on the dashboard tip-box matches the
top-pattern bar — the same signal surfaces twice, no
hard-coding.

**Don't** linger here. The dashboard is the trust-building
opener; the predictions live in the next four beats.

---

## Beat 2 — Smart Search (25 s) — demo moment #1

Click **Smart Search**.

> "Type `food`, classic e-commerce query. On the left, plain
> token match — dog food at the top because the catalog is dog-
> heavy. Now I switch the customer pill to Maija, a cat owner."

Click the **Maija** pill.

> "Same query string. The right column is now entirely cat food
> — Whiskas, Acana cat lines, Orijen indoor cat. Every row in
> the predictive column has a gold ★ — none of those products
> are in the baseline top 10. The Aito panel shows the live
> `_recommend` body: same `name $match food` filter, plus
> `goal: {customer_segment: cat_owner}`."

Click **Saara** (large-breed dog).

> "Switch to Saara — large-breed dog owner — and the predictive
> column flips again. Now it's Acana, Hill's Science Plan,
> Eukanuba large-breed kibble. Royal Canin drops out — the
> brand a generic-search engine ranks at the top, Aito puts
> further down because Saara's segment buys those specialised
> brands."

**The phrase to say**: "same query, different list per
customer." That's the moment.

---

## Beat 3 — For You (15 s) — demo moment #2

Click **For You**.

> "Same idea, no query string. Pure recommendation grid for the
> selected customer. Maija — cat litter and cat dry-food. Olli
> — small-dog accessories, grooming, health. Saara — large-
> breed dog kibble. The browser latency badge in the top bar
> shows the actual round-trip time — Aito returns this in tens
> of milliseconds."

Click each persona in turn to show the flip live. The grid
re-ranks visibly under 300 ms (a screen-recording will show
it as instant).

> "Three crisply different shoppers from one underlying query
> shape. The Aito panel on the right shows the exact
> `_recommend` body that ran for each — the `goal` field
> changes per persona; nothing else does."

---

## Beat 4 — Bought Together (15 s) — demo moment #3

Click **Bought Together**.

> "Now we drill into the headline: anchor is dog dry-food.
> Cross-sell tiles — dog dental treats at × 2.7, dog wet-food
> at × 1.5, dog treats at × 1.5, dog accessories at × 1.6. The
> Aito panel shows the live `_relate` body — that's exactly the
> query the dashboard's top-patterns row quotes. **Same data,
> live recompute, no precomputed cross-sell tables.**"

Pick another anchor — say cat litter — to show the picker live.

> "Pick cat litter — top cross-sells are cat dry-food at 2.28×
> and cat wet-food at 2.14×. Cat litter buyers stock up on cat
> food in the same basket. Real co-occurrence, no rules, no
> manual tagging."

---

## Beat 5 — Product Filling (15 s) — demo moment #4

Click **Product Filling**.

> "Catalog enrichment. This row — Hill's Science Plan Sensitive
> Turkey Dog Food 2kg — is missing weight, dietary, and tax
> class in the catalog. On the right, Aito fills five fields:
> pet type 98 %, category 87 %, weight 98 %, dietary 95 %, tax
> class 98 %. All from the product name plus the brand. Five
> `_predict` calls in parallel, end-to-end in under half a
> second."

Hover the **?** icon on the **dietary** row.

> "Click the `?` icon and you get the `$why` decomposition — the
> tokens in the product name that drove the prediction:
> 'Sensitive', 'Turkey', 'Dog Food'. Every prediction is
> auditable down to the contributing words."

---

## Beat 6 — Evaluation (20 s) — demo moment #5

Click **Evaluation**.

> "Last view. Aito's `_evaluate` runs each model against a held-
> out test set. Pet type from name — 97.5 % accuracy. Dietary
> from product attributes — 71.5 % accuracy at +47 percentage
> points over baseline. Customer segment from product — 80.5 %
> at +34 pp."

Pause. Point at the bottom row.

> "And then Return Risk. 96.5 % accuracy — looks impressive,
> right? The gain is **plus zero point zero**. Aito learned
> nothing the prior didn't already know. About 3 % of lines get
> returned in this data; without specific signal, the model
> just predicts 'won't be returned' for every line and is 97 %
> correct by accident."

Tap on the failed row to show the Aito panel updating.

> "This is the part most demos hide. Aito tells you when it
> can't predict. That row would be a disaster on a production
> deployment under any metric that wasn't accuracy_gain. You
> see the failure here so you don't ship a fake model."

---

## Beat 7 — Markdown decision (15 s) — demo moment #8

Click **Markdown** in the Operate section.

> "We have €14k of tied capital across 15 overstock SKUs. For
> each one, Aito ran `_estimate units_sold` at five price points
> — list price, minus 5, 10, 15, 20 percent. The view picks the
> markdown that clears the excess in three months at the highest
> recoverable margin."

Point at a row where the proposed discount is 0 %.

> "Notice this row — Aito says 'no discount needed; existing
> demand clears the excess'. It's not a 'discount everything'
> button. It's 'discount exactly what needs discounting'. Real
> merchandiser thinking, automated."

Click into the row to expand the curve.

> "Five `_estimate` probes per SKU, chosen row highlighted.
> Whole sweep takes 18 seconds cold across the 15 overstock
> SKUs. Cached for 30 minutes after."

---

## Beat 8 — Win-back campaign (20 s) — demo moment #9

Click **Win-back** in the Operate section.

> "Churn told us who's at risk. Win-back answers what to do
> about the customers who already left. Top 20 churned
> customers by lifetime value. For each one, Aito's
> `_recommend` runs against a historical campaigns table —
> goal: `responded = true`. Returns the products with highest
> predicted email response rate."

Point at the KPI strip.

> "€1,354 in predicted recoverable revenue across 20 emails
> costing €30 to send. That's a 45× ROI. Average response rate
> 58% — strong because we're picking the top-ranked products
> per customer, not blasting everyone with the same offer."

Click into a row to expand.

> "Three product cards per customer, each with response
> probability, predicted AOV, and the resulting expected €.
> This is exactly the action-and-impact pattern our accounting
> demo uses for support escalations — same Aito shape, e-com
> outcome label."

---

## Beat 9 — close (10 s)

> "Sixteen views. Six `_predict`, four `_recommend`, three
> `_relate`, two `_estimate`, one `_evaluate`. One Aito DB. No
> retraining, no MLOps, no models to operationalise. The same
> JSON body that runs in the panel is the call your frontend
> would make. EU hosted, no PII stored."

Pause. Look at audience.

> "Predictive e-commerce in roughly fifteen hundred lines of
> Python and three thousand lines of TypeScript. Source is on
> GitHub — every panel has a link."

---

## Quick recovery — if a moment doesn't land

| Symptom | Recovery |
|---|---|
| Smart Search doesn't flip (Saara still shows cat food on right) | Hit refresh — likely a cache leak from a previous session. The first cold call takes ~600 ms then the cache warms. |
| For You returns empty | Backend hasn't loaded. Run `./do load-data`. |
| Pattern Explorer / Bought Together returns 400 | Schema regression. Run `./do reset-data`; the `orders.line_categories` Text column needs the denormalised tokens. |
| Evaluation row stuck at 0/0/0 | Aito timed out on `_evaluate` (cold path is ~30 s). Wait a few seconds and refresh. |

---

## Common questions

**"How fresh is this data?"**
Twenty-four months of synthetic PetNord orders generated by
`data/generate_fixtures.py` with a fixed RNG seed. Regenerate +
re-upload with `./do reset-data` whenever the catalog changes.

**"Does Aito learn the user's history?"**
Not per-individual — 3 000 customers × ~4 orders each is too
thin for per-customer priors. Aito conditions on the customer's
*segment* (≈ 600 customers per group). Per-customer learning
needs an order of magnitude more data and a different schema
shape — `aito-shopify` shows that pattern.

**"How long would a real merchant's data take?"**
The full PetNord load takes ~50 s end-to-end. Per the framework
doc, productive demos run on Aito's free tier with ≤ 100 k
rows.

**"What about new SKUs with no history?"**
Aito's `_predict` reads off Text tokens in the product name
(see Beat 5, the Filling moment). A brand-new SKU with a
descriptive name predicts well from day one — no cold-start.

**"Is this open source?"**
Yes — every panel links to the GitHub source. The repo includes
ADRs documenting each query shape and the Aito gotchas we
found while building (see `docs/aito-cheatsheet.md`).
