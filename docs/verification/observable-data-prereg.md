# Pre-registration: only what a shop can observe (ADR 0033)

Written 2026-10-19, **before** the generator changes for ADR 0033. It
builds on ADR 0032's data and checks (`product-states-prereg.md`), which
are re-run unchanged: the planted effects P1–P5 against their nulls, and
the absolute P2a and P6. Every threshold below is fixed now; any change
is an amendment here first, with its reason.

## What changes in the data

- **Removed from every table Aito sees:** `lifestyle`, `health_focus`,
  `treat_affinity`, `brand_loyalty`, `segment`, and every `customer_*`
  copy of them on `order_lines`, `impressions`, `winback_campaigns` and
  `customer_months`. They stay in the generator and still drive behaviour.
- **`customers`** holds what was declared or recorded: `region`,
  `tenure_months`, `pets` (the household's pet types, whitespace Text),
  `dog_size` (when a dog is among them), `diet` (the household's rule),
  and the history aggregates it has today (`total_orders`,
  `total_spent_eur`, `last_order_month`, `churned`).
- **`contexts`**, one per impression session: `customer` (link),
  `month`, `weekday`, `surface`, `basket`, `basket_categories`,
  `prev_basket`, `owned`, `search_query`.
- **`impressions`**: `context` (link), `product_sku` (link, the
  recommend target while `product_state` candidates overconfide,
  td-20261018112625647694), `product_state` (link), `position`,
  `just_bought`, `clicked`, `added_to_cart`, `purchased`.

## The planted effect

| # | Effect | Planted as |
|:--|:--|:--|
| K1 | The kit's next item | The household's kit is read from the session's basket **and** what it owns from earlier orders. An impression of a kit item it already owns converts at odds ×0.1; the kit's next missing item (the starter kit's partner, then `ADD_ONS` in order) ×5; another add-on not yet owned ×1.5. It replaces ADR 0030's S6 rule for kit add-ons (×3 when the starter kit is in the basket); S6's dental-with-dry-food rule stays. |

## 1. Data checks

| # | check | pass when |
|:--|:--|:--|
| O1 | no column named after a hidden trait, nor `segment`, in `src/schema.py` or in any fixture row | none |
| O2 | every impression's context exists and belongs to the impression's customer and month | 100 % |
| K1a | (null: K1 off, S6's kit rule kept) purchase rate of the kit's next item ÷ that of other not-yet-owned add-ons, on impressions where the household has a kit | planted ÷ null ≥ 2.0 on seeds 42, 7, 99 |
| K1b | (same null) purchase rate of an owned kit item ÷ the same item unowned | planted ÷ null ≤ 0.3 on every seed |
| D/S/P | ADR 0030's and 0032's checks | as registered; a range that moves is amended here first |

## 2. Aito checks (on a test env, after #1673 is on shared)

| # | check | pass when |
|:--|:--|:--|
| R1 | hit@10 on held-out impressions: `_recommend` with the customer as evidence (`context.customer`) and the context | reported against today's ranking (segment and traits handed over); the Shop uses it if the paired 95 % CI's lower bound is above −0.05 |
| R2 | the same with the customer as the population (nested `from`, fallback to all) | reported; the better of R1 and R2 is used |
| R3 | `$why` under R1 | the context's lifts nest under the product's own lift, as the Shop's reasons need |
| R4 | `_relate` over `context.customer.dog_size` (two links) | answers with counts that match a `_search` count |
| R5 | the grid for a guinea-pig owner | cage in the basket, nothing owned: water bottle in the top 3; owns cage and bottle, empty basket: hideout in the top 3 and no cage in the top 12 |
| R6 | a premium, health-focused cat owner (traits known to the generator only) | their grid's food is mostly premium and wellness: share ≥ 1.5× the catalogue's |

## Amendment after the first Aito run (2026-10-20, decided with Antti, before any R5 re-run)

R5 failed on env `observable` (Aito 2.11.8): Päivi owning cage and bottle saw
treats first and the hideout at #24. Diagnosis (probes in
`scripts/kit_absence_probe.py`): Aito's `$p` matches the data's counts per
product (Fruit Drops 0.43 vs 31/76 bought; Exercise Wheel 0.31 vs 5/16), and
the kit lifts its add-ons ×2–3. Two causes, neither an engine error:

1. **The query left evidence out.** `context.owned: {$and: [$match cage,
   $match bottle]}` also matches households that own a hideout, for whom a
   hideout never sells, so its lift was diluted to ×1.6. `_recommend`
   doesn't infer absence from `$match` (by design; Aito core
   td-20261020203235895741 is to widen absence evidence to `_recommend` and
   link paths).
2. **In this data, treats outsell even the kit's next item** for these
   households (≈ 0.4 against ≈ 0.38 at best), and "next" is often the wheel,
   because a hideout bought that month is in the basket, not in `owned`.

**Change (query, not data):** the Shop's context also states which commonly
owned items the household lacks, learned from the data: the 8 items most
often owned by households that own what this one owns (`_relate` over
`contexts.owned`), each absent one as `{"$not": {"$match": token}}`. No kit
knowledge in the app. Probe: the wheel moves #9 → #3 (×3.1 → ×4.4), the
hideout #24 → #10.

**R5 becomes:** for Päivi owning cage and bottle, with an empty cart, *a* kit
add-on she lacks (hideout, wheel or tunnel) is in the grid's top 3 and no
cage in the top 12; as of February 2026, owning nothing, with a cage in the
cart, the water bottle is in the top 3. K1's strength is unchanged.

## Amendment: R1/R2 as a parameter sweep of the Shop's query (2026-10-20, Antti, before any run)

Antti asked to tune the Shop's query as a data scientist would, not by
hand-picked scenarios. R1/R2 become a held-out sweep
(`scripts/shop_query_sweep.py`):

- **Sample:** 150 sessions (contexts) drawn with seed 0 from those that
  showed at least one product that was bought, months 2025-05 … 2026-04.
- **Leave the session out:** each query reads
  `from: {from: impressions, where: {"$not": {"context": <session>}}}`,
  so the session never grades itself.
- **The query** is the Shop's own `where`, rebuilt from the session's
  observed context: customer, month, cart (that month's basket), owned kit
  plus the learned absences, `just_bought: false`.
- **Variants:**
  - A, the Shop today: cart as words, absences, no `basedOn`;
  - B, A without absences;
  - C, A with cart SKUs + words;
  - D, A with `basedOn: ["pet_type"]`;
  - E, A without the customer;
  - F, A without the cart and kit (customer + month only).
- **Metrics:**
  - hit@12, whether any product bought in the session is in the top 12;
  - Brier score of `$p` over the products the session showed. The cards
    show `$p`, so calibration matters.
- **Decision rule:** the Shop uses the variant with the highest hit@12
  whose Brier score is within 0.01 of A's. If D wins on hit@12 but
  fails on Brier, it ranks with D and shows A's `$p` (two calls).
  Differences under 2 sessions (≈ 1.3 pp) are not a win.

## Results

### Data checks, 2026-10-19 (seed 42 committed; seeds 7 and 99 by `./do planted-effects`)

| check | result |
|:--|:--|
| O1 no hidden-trait column in the schema or any fixture row | pass (`tests/test_observable_data.py`) |
| O2 every impression's context exists and is its month | pass |
| K1a the kit's next item ÷ other add-ons, planted ÷ null | 2.47, 2.48, 2.16 (≥ 2.0): pass |
| K1b an owned kit item ÷ unowned, planted ÷ null | 0.023, 0.014, 0.019 (≤ 0.3): pass |
| P1–P5 (ADR 0032), re-run on this data | 31 of 32; P2d misses on seed 42 (1.14 ≥ 1.25), as reported before |
| D/S checks | pass (`./do test`, 312 tests) |

The hidden traits are verified through `data/answer_key/customer_traits.json`,
which the loader never uploads.

### R1/R2 sweep, 2026-10-20 (shared 2.11.8, env `observable`, 150 held-out sessions)

Pre-registered variants, `scripts/shop_query_sweep.py`:

| variant | hit@12 | Brier | sessions vs A (won / lost) |
|:--|--:|--:|:--|
| A, the Shop today | 0.153 | 0.2273 | — |
| B, no absences | 0.200 | 0.2220 | +7 / −0 |
| C, cart SKUs + words | 0.140 | 0.2376 | +3 / −5 |
| D, `basedOn: [pet_type]` | 0.167 | 0.2322 | +3 / −1 |
| **E, no customer** | **0.227** | **0.1774** | **+17 / −6** |
| F, customer + month only | 0.133 | 0.2058 | +6 / −9 |

**By the rule, E wins:** the highest hit@12, and a Brier score 0.05 better
than A's. Conditioning on the customer's identity (`context.customer`, about
40 impressions each) overfits and overconfides on held-out sessions. The
learned absences, which lift Päivi's kit in the named scenario, cost hit@12 on
average (B beats A, +7/−0). Any variant added after this run is exploratory
and reported separately.

Exploratory, added after the run above (not part of its decision rule;
`--exploratory`, same 150 sessions, A–F reproduced exactly):

| variant | hit@12 | Brier | sessions vs A (won / lost) |
|:--|--:|--:|:--|
| G, declared pets (`context.customer.pets`) in place of identity | 0.220 | 0.1754 | +15 / −5 |
| H, no customer and no absences | 0.227 | 0.1749 | +18 / −7 |

Declared pets do as well as no customer, and keep a signal for a shopper
with an empty cart. Once the identity is gone, the absences neither help nor
hurt on average (E vs H).

**Correction (2026-10-20, from the benchmark lane, dev3).** An independent
local rebuild reproduced the table above exactly on the same 150 sessions.
But a second, equally valid 150-session draw from the same pool (6,824
eligible sessions) gave E − A hit@12 = −0.013 [−0.067, +0.040], a tie, against
+0.073 [+0.013, +0.133] here. So at n = 150 the **hit@12** difference is not
resolved. **Calibration is:** E's Brier was better on both samples, with
paired intervals excluding 0 (−0.048 here, −0.026 on theirs), as were B's and
F's. The decision on the Shop's query waits for dev3's run over the whole
pool. (Their note for anyone rebuilding the sweep: `random.Random(0).sample`
and a seeded `shuffle(...)[:150]` draw entirely different sessions.)

