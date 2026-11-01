# ADR 0056: Planted incidents: one loud batch recall and three quiet quality problems

**Status:** Accepted (2026-11-01, Antti: "Merge and implement"); built behind switches that are off in the committed fixtures, see the amendment
**Amendment 2026-11-01 (found when building):** a single SKU sells about five units a month here, too few for a batch to leave a mark a check could tell from noise. So an incident hits a *line* of SKUs found in the catalogue by name (E1: the grain-free salmon dog foods, three to eight of them by seed, written under the house label *PetNord Grain Free Fish Adult Dog Food*; E2: Sheba beef cat food; E3: the house-label liver treats; E4: the house-label hamster mix), and the recalled line sells better before it fails (a hit: pick factor ×4 from 2025-01), so its failure has weight. The switches `E1`–`E4` are **off** in the committed fixtures, which a test shows are byte-identical to before; the release that carries the incidents flips them on, regenerates and reloads. `./do planted-incidents` judges them with the switches on.
**Date:** 2026-11-01
**Deciders:** Antti

## Context

The demo's data is generated, and each pattern an Aito feature should find is planted on purpose and
checked against a null generation (ADRs 0038–0040, 0049; `data/planted_switches.py`). So far the planted
patterns are about how shoppers respond to offers, stars, sources and prices. Nothing in the data is an
*incident*: a thing that happened to a product at a time, that moved sales, feedback and churn together, and that a
shopkeeper would want to find by cutting the data over time (the period selection of ADR 0055).

Two kinds of incident happen in a real pet shop, and they differ in what the shop knows:

- **A loud one.** A production batch of a dry dog food made dogs ill. It was in the news, the product was pulled, and
  customers lost trust in the product type. The shop knows when it started, and when it was pulled.
- **A quiet one.** A customer gets two bad units of a product in a short time, complains and is refunded, and switches
  to another brand for good. The shop holds the complaints but not the cause, and nobody ever says when the product
  is fine again, so the customers who left do not come back.

The demo is the fictional PetNord. No real retailer, brand, product or news story appears in data, code or text.
The catalogue's brands are real names used as realistic fixtures, so **no incident is put on one of them**.

## Decision

Plant four incidents, each behind its own switch (`E1`–`E4`) with its own seeded RNG streams, so a null generation with one
switched off changes only what that incident touches.

| | Incident | Where | When |
|---|---|---|---|
| E1 | **Loud**: a batch of a grain-free fish dry dog food, two pack sizes, made customers' dogs ill. Pulled after the news. | two SKUs of one catalogue line, renamed to a fictional house label | batch sold in 2025-09 and 2025-10; pulled from 2025-11 |
| E2 | **Quiet**: bad units of one cat wet-food product | one SKU | one month in 2025-02 |
| E3 | **Quiet**: bad units of the house-label dog treats | the line | two months, 2025-06 and 2025-07 |
| E4 | **Quiet**: bad units of one small-animal dry food | one SKU | one month in 2026-01 |

The dates are inside the data (2024-05 to 2026-04). The real event predates it, so this is a fiction in its own right.

### E1, the loud one
1. **The batch.** A purchase of the two SKUs in the batch months has the experience *bad* with probability 0.35 (it is about 0.05 otherwise). The
   existing chain does the rest: a bad experience is returned more often, is reviewed (category: quality, symptoms in the text, never deaths),
   lowers the order's NPS and raises the churn hazard (R3, R4, A7).
2. **Pulled.** From 2025-11 the two SKUs are not in the shop's product list and are not bought again: sales are zero, in every view.
3. **Trust.** From 2025-11, the odds to buy any other grain-free dog dry food are ×0.70 and recover linearly to ×1.00 over eight months.
   The customers who bought the batch are ×0.5 on that type for the same eight months.

### E2–E4, the quiet ones
1. In the incident month a purchase of the product is *bad* with probability 0.30. The customer's complaint, refund (a returned line) and a low review follow from the existing chain.
2. **Not pulled, no state change, no signal that it is over.** The product keeps selling to everyone else.
3. **They switch for good.** A customer who had a bad unit has ×0.05 odds on that product for the next 12 months, whatever happens to its quality.
   Their purchases go to the other products of the category. A customer who did not have a bad unit buys it as before.

### What a null changes
Switching `E1` off removes the batch, the withdrawal and the trust dip; `E2`, `E3` and `E4` each remove one quiet incident. Common random numbers
keep every other draw where it was. The catalogue keeps the same number of products (two SKUs are renamed), so no draw shifts.

### The answer key
`data/answer_key/incidents.json` holds each incident: the SKUs, the months, the customers who had a bad unit, and the product they moved to.
The app does not read it. A test does, to check that what the data shows is what was planted.

### The checks (pre-registered, each against its null on seeds 42, 7 and 99)
- E1: units of the line in the batch months are at least 2× the null's (the hit), and zero from 2025-11 while the null still sells it. The bad-experience share of the batch is at least 3× the null's.
  Average review rating of those SKUs in the batch months is at least 1 star lower. Grain-free dog dry food ex-batch is at least 5 % lower in the month after the
  pull than in the null. Customers who bought the batch churn at least 1.3× the null's rate in the following 8 months.
- E2–E4: bad experiences on the SKU in the month are at least 3× the null's, and reviews of 1–2 stars and returns on it rise with them. The affected customers'
  repeat purchase of that SKU in the next 12 months is at most one third of the null's, while the other buyers' repeat purchase is within 10 % of the null's.
- Everything else: the other planted effects' checks still pass (`./do planted-effects`).

## Aito usage

None new. The incidents are in the data, and the existing views find them: the Customers trend and period (ADR 0055),
Reviews, NPS, Retention and Supply. A release that carries them is a new data release (ADR 0049): reload the shared
database, precompute, then deploy. Figures quoted in articles change with it.

## Acceptance criteria

- [ ] `./do generate-fixtures` produces the same fixtures with the incidents switched off as it does today, apart from the renamed SKUs.
- [ ] `./do planted-effects` reports E1–E4 and every check above passes on all three seeds.
- [ ] A user can pick 2025-09 to 2025-12 in the Customers trend, tick *Diet: grain-free*, and see the segment's revenue fall after the batch months.
- [ ] A user can open the house-label product's reviews and see a cluster of 1-star reviews in the batch months and none after the pull.
- [ ] No text, name or number in the repo refers to a real retailer, brand or news story for these incidents.

## Demo impact

`docs/demo-script.md` gets a short "what happened to the house-label fish food" path, after the data release is loaded.

## Out of scope

Loading the new release into shared Aito and deploying it (Antti's decision, after the quoted figures are re-checked); an automatic incident detector in
the app; a delivery-partner problem, a supplier stock-out and a competitor promotion (possible later incidents with their own switches).

## Amendment 2026-11-01, after the first judgement
The first run of `./do planted-incidents` passed 16 of 19 checks (docs/verification/planted-incidents-data.md). With Antti's "Fix those": the trust dip is
×0.70, not ×0.90 (substitution to other grain-free food outweighed ×0.90); the recall's churn is its own larger hazard (×6, then ×8 after the second run, for eight months); E3 runs for two months and covers all the house-label dog treats, to give the check
enough customers; and the trust check reads only customers who never bought the recalled line, since those who did switched to other grain-free food. The second run still failed
E1-trust (the first definition), E1-churn (1.28 against 1.3) and both E3 checks, which led to the last three changes. These were changed after seeing the data, which the report says.
