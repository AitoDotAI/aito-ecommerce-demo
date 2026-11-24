# Pre-registration: data release 6 (realistic showings, fictional brands, a large profile)

Written 2026-11-24, **before** any generator change, on Antti's decisions of 2026-11-23 (items 3, 4 and 8 of
`~/episto/ai/log/2026-11-23-ecommerce-decisions.md`; board ticket td-20261124130721630361). DRAFT: the band in section 2 is a
PROPOSAL for the CPO and Antti; nothing below is fixed until this file is merged. After the merge every threshold is fixed, and
any change is an amendment here first, with its reason.

## 0. What stays pinned

Release 5 is not touched. `data/` as committed (the files `data/release-env.json` counts, env `experiments-data`), the live demo
and every number quoted from it stay what they are. A new test records the sha256 of every file release 5 holds under `data/` today
and fails if any of them changes. The generator's default run (no new option) must still write those bytes (`R0` below).

Release 6 is written to its own directory, `data/releases/release6/`, by an explicit option (`--release 6`, with `--profile small`
or `--profile large`). The loaders, the data release gate and the `./do` commands take the release directory as an option too, so
release 6 is loadable and not only generated. Only the small profile and a manifest are committed:
`data/releases/release6/small/<table>.json`, `data/releases/release6/manifest.json` (per profile and table: row count and sha256;
the generator's git revision; the seed). The large profile is generated on demand and never committed; its manifest entry is.
Loading either profile into a shared env is Antti's step (ADR 0035); release 6 goes only to the local source-built engine until he
says otherwise.

## 1. What changes, and what must not

| # | change | how |
|:--|:--|:--|
| C1 | Purchases per showing fall into a realistic band (section 2) | The sales stay as they are; the showings that were not bought are added (section 3) |
| C2 | Fictional brands | One fixed mapping from each real brand to an invented one, applied to every row and every text the generator writes (section 4) |
| C3 | A large profile | ~10,000 products, ~50,000 customers, ~150,000 baskets, ~1,000,000 impressions; the planted counts scale with the catalogue (section 5) |

What must not change in the small profile, apart from the brand strings: customers, products (except names and brand), orders,
order lines, reviews and NPS answers (their texts with the new brand names), and every planted effect judged on sales. Checks
`S1` and `S2`.

## 2. The band (PROPOSED)

Measured on release 5, seed 42 (2026-11-24): 94,536 impressions, purchases per showing **0.227** overall; by placement
`buy_again` 0.825 (n 17,452), `checkout` 0.907 (n 1,221), `list` 0.079 (n 75,863). 21,457 purchased showings against 35,972 order
lines (the rest are `direct` sessions, ADR 0045). The two near-certain surfaces drive the overall rate: today a buy-again or
checkout showing is recorded almost only when it is bought.

Proposed, for the CPO and Antti to set. These are not measured and come from no cited source. They are the orders of magnitude a
merchant would recognise:

| placement | purchases per showing |
|:--|:--|
| `list` (landing, category, search, for you, bought together) | 0.01 to 0.04 |
| `buy_again` | 0.10 to 0.30 |
| `checkout` | 0.03 to 0.15 |
| all showings | 0.02 to 0.08 |

## 3. How C1 is planted (proposed: add the unbought showings, keep the sales)

Two ways were considered:

- **A (proposed).** Every session draws its sales exactly as today: the same streams, the same purchased showings, the same order
  lines. To that we ADD showings that were not bought:
  - the buy-again strip shows more of the household's earlier products than it buys (up to a fixed strip length);
  - the list is longer (later positions);
  - checkout shows more than the one dental chew.

  Each added showing draws its click from the same funnel as today (position, listing quality), from a NEW keyed stream
  (`stream(RNG_SEED, "unbought", ...)`), and it is never a purchase. So no existing draw moves, the sales are byte-identical
  (apart from the brands), and every planted effect judged on sales stays valid. The cost: an effect judged as a per-showing
  purchase rate is diluted, by the same factor for every product of a placement. Its direction and ratio hold; its absolute
  rate falls (`S3`).
- **B.** Lower the purchase odds and show more. The sales are redrawn, so every planted judgement of this repo and of aito-shopify
  must be re-run on seeds 42, 7 and 99. It is more realistic per showing and much more work. It is not proposed.

The strip length, list depth and checkout count are chosen so that the medians of seeds 42, 7 and 99 fall in the middle of the band
(section 2). The values are written here as an amendment BEFORE the checks are run.

## 4. How C2 is planted: the brand mapping

The house label `PetNord` stays: it is the fictional shop's own. Every other brand maps to an invented name of the same tier and
categories (`PREMIUM_BRANDS`, `MASS_BRANDS` and `BRAND_CATEGORIES` are re-keyed, not reshaped). The mapping (PROPOSED; each name
is checked against a trademark and web search before the release is cut, and replaced here if it is taken):

| release 5 | release 6 | tier |
|:--|:--|:--|
| Royal Canin | Aurelian Vet | premium |
| Hill's Science Plan | Fernholm Nutrition Plan | premium |
| Acana | Tundrafield | premium |
| Orijen | Wildmarrow | premium |
| Eukanuba | Kestrova | mass |
| Whiskas | Purrsy | mass |
| Felix | Mizzo | neutral |
| Sheba | Velvetbowl | neutral |
| Whimzees | Chewbrite Twists | neutral |
| Kong | Bounderoo | mass |
| Trixie | Pikkutassu | mass |
| JBL | Clearfin | mass |
| Tetra | Aquadotte | mass |
| Beaphar | Herbaro | mass |

The names are applied where the generator writes them: product names (`_compose_name`), tags, review and NPS texts
(`feedback_text.py`), the answer key and the evidence files the release writes. Docs, ADRs, screenshots, precomputed snapshots
and tests in this repo that quote release 5 keep its names: they describe release 5. Anything shown OUTSIDE is taken from release
6 (`B1`).

## 5. How C3 is planted: the large profile

Sizes (Antti, 2026-11-23): about 10,000 products, 50,000 customers, 150,000 baskets (orders) and 1,000,000 impressions. More
products come from more variants per (brand, pet type, category) and more brands per tier: invented names, generated by the same
rule as section 4. Antti's option A: planted counts scale with the catalogue. A planted effect that names N products (incidents,
recalls, launches, price rises, offers) names N × (products ÷ 658), rounded, chosen by the same rule. Rates and multipliers are
unchanged. The large profile carries the brand mapping and C1's band too.

## 6. Checks

Every check runs on seeds 42, 7 and 99 unless it says otherwise. **Fail first:** F1 and B1 are run on release 5 before the
generator changes and must FAIL there (F1: 0.227 and 0.825 are outside the band; B1: release 5 names real brands). A check that
passes on release 5 checks nothing.

| # | check | pass when |
|:--|:--|:--|
| R0 | the default run, and `data/` as committed | byte-identical to release 5's recorded sha256 (every file) |
| F1 | purchases per showing, overall and per placement, release 6 small | inside the band of section 2, on every seed |
| F2 | the funnel's order (purchased ⇒ added to cart ⇒ clicked) on every impression; ADR 0045's tests (units sold = purchased order lines; every purchased impression has its order line) | 100 %; the tests pass unchanged |
| S1 | orders, order lines, customers, reviews, NPS answers of release 6 small against release 5 with the brand mapping applied | byte-identical after the mapping |
| S2 | every planted effect of this repo judged on sales (ADR 0056 incidents, the churn tells, the experiments) | the same verdicts as release 5 (they read the same rows) |
| S3 | every planted effect judged on showings (listing odds, the price curve, position, K1) | the same direction, and its ratio within ±10 % of release 5's. The absolute rates are reported, not judged |
| B1 | no release-5 brand name in any file of release 6 (whole word, case-insensitive; `Hill's` with either apostrophe) | none |
| B2 | the mapping is one to one, keeps tier and categories, and no invented name equals a release-5 name or another invented one | holds |
| B3 | each invented name has been checked against a trademark and web search; the result is written next to the table | done before the release is cut (a person's step, recorded) |
| L1 | large profile sizes | each within ±10 % of section 5 |
| L2 | large profile: F1, F2, B1 on seed 42 | as above |
| L3 | large profile: the planted counts | N × (products ÷ 658), rounded, for every planted list |
| M1 | the manifest | it lists every table of each profile with its row count and sha256, and the files match it |

## 7. Downstream (aito-shopify)

- aito-shopify's gates identify their dataset by connector and count. Before release 6 merges, they are keyed to the release
  version or the manifest hash, with a fail-first test, so that a new release with the same counts reads as UNTESTED (CPO,
  2026-11-24). The first is the review-triage gate.
- Book 8 (trending) and the screenshots are re-recorded on release 6. The embedded Shopify shot of 2026-11-24 was taken on release
  5 and labelled "internal: real brands"; it is retaken on release 6 before any shot goes outside.
- The file layout of section 0 is what platform's scale harness reads (`data/releases/release6/<profile>/<table>.json`).
