# ADR 0044: What a shop can know about a person

**Status:** Accepted (2026-10-24, Antti: "we should list things we can realistically know of
a person, like purchases, impression/behavior data (on consent), details on purchase form
(name, sex, location) and possible interests (if he has selected such)")
**Date:** 2026-10-24
**Deciders:** Antti

## Context

ADR 0033 removed hidden generator traits from everything Aito reads: "only what a shop
observes". Two things still aren't realistic:
- **Behaviour is recorded for every shopper.** A real shop records impressions, clicks and
  carts only for shoppers who consented (cookies or analytics consent). For the rest it
  has purchases and what they typed into forms.
- **What a person declares is thin.** Today it's pets, dog size and a diet rule. Real shops
  also have the purchase form (name, postcode, optionally sex) and interests the person
  chose on a preferences page.

Partners ask about this directly: what does personalisation do for a shopper who said no
to tracking?

## Decision

### What a person's data may hold

| Source | Fields | Recorded for |
|---|---|---|
| Purchases | orders, lines, prices, returns | every customer (needed to fulfil the order) |
| Purchase form | name, postcode area (first 3 digits), region, delivery method; **sex**, optional | every customer; sex only if they filled it in (about 55 %) |
| Account | joined month, sign-up source (ADR 0040), loyalty member | every customer |
| Declared preferences | pets, dog size, diet rule (as now); **interest topics** chosen from a fixed list (training, grooming, natural food, toys and play, health and care, budget buys), newsletter opt-in | only those who set them (topics: about 35 %) |
| Behaviour | impressions, clicks, add-to-cart, search queries | **only shoppers with behavioural consent** (about 60 %, a `consent_behavioural` flag on the customer) |

Consent is recorded on the customer, and the generator writes no `impressions` or
`contexts` rows for a session of a non-consenting shopper. Their orders still exist. Their
hidden traits still drive what they buy, so Aito can learn about them only through
purchases and declarations.

### How the views use it

- **Personalisation degrades visibly, not silently.**
  - For a non-consenting shopper, the Shop uses purchases and declared fields only. Its
    panel says so: "No behavioural data (no consent): picked from purchases and what they
    told us."
  - A persona of each kind is in the Shop's shopper list.
- **Sex is not used to rank products.** It's available to analytics (Patterns' "who buys
  what"), with the row marked as a declared field. A test asserts that no ranking query
  conditions on it. Recommending by sex is legal but rarely wanted, and a partner should
  see that choice made deliberately.
- **Interest topics** are declared evidence the Shop may use (`context.customer.interests`
  `$match`), like declared pets.
- **Evidence: "What consent costs".** The Shop's hit@k for consenting and non-consenting
  shoppers, held out, with intervals, pre-registered. It's synthetic, so it shows the
  mechanism, not real-world sizes.

### Planted effects (pre-registered in data release 2's prereg)

| # | Effect |
|---|---|
| C1 | Interest topics are informative: a shopper declaring "natural food" buys grain-free and natural-diet products at ≥ 1.8× the rate of others (from the hidden health focus, so it's a consistent declaration, not a new cause) |
| C2 | Consent is independent of the hidden traits (no selection effect), so "what consent costs" measures missing data, not different people |
| C3 | Sex has no planted effect on purchases. Patterns must show no clear lift for it; the test of the significance bar is that it finds none |

## Aito usage

No new query shapes: interests are a Text field with `$match`, as `context.customer.pets`
already is. The Shop's non-consenting path is the existing household query without
`context.*` behaviour conditions; it's probed before use.

## Acceptance criteria

- [ ] Customers carry `consent_behavioural`, `sex` (nullable), `postcode_area` and
      `interests` (nullable); no impression or context belongs to a non-consenting
      customer (test).
- [ ] The Shop shows a non-consenting persona with the "no behavioural data" note, and
      its picks come only from purchases and declarations.
- [ ] No ranking query conditions on sex (test).
- [ ] C1–C3 pass their pre-registered checks; "What consent costs" is an Evidence entry
      with intervals.

## Out of scope

- Real consent management (banners, revocation flows).
- Age (rarely on a pet shop's form). Add it with a reason if a partner asks.
- Inferring sex or other sensitive attributes from behaviour. We don't, and the views
  say so.

## Consequences

**Good:**
- The data matches what a shop really holds, and the demo answers the privacy question
  with a measured number.
- Declared interests give the Shop an honest cold-start signal.

**Bad:**
- About 40 % fewer behaviour rows; some planted behaviour effects lose power, and their
  checks are re-run.
- One more persona and one more Evidence entry to maintain.
