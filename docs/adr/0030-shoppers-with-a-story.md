# ADR 0030: Shoppers with a story — personas, guided kits, seasons, routines

**Status:** Accepted (2026-10-12)
**Date:** 2026-10-12
**Deciders:** Antti

## Context

The demo's predictions are only as interesting as the patterns in its
data, and today's data has few. Antti's review (2026-10-12) compared it
with the older grocery demo (demo.aito.ai), which he still uses to show
Smart Search:

- **Grocery shoppers have a story.** Each persona has a line of
  narration ("lactose intolerant", "vegan") and preferences that follow
  from it, so a search or a recommendation visibly changes per person.
  Here, three hand-built personas carry a few soft traits, with no hard
  rules and no narration.
- **Pet purchases come in bundles.** A new hamster means a cage, a
  house, bedding, a water bottle and food, roughly in that order.
  A good shop guides you through it. ADR 0027 plans starter kits and
  add-ons in the data (branch `feat/lifecycle-data`, not merged or
  loaded yet), but no view shows them.
- **Routine buying.** A cat-and-dog household buys the same foods and
  treats every few weeks. ADR 0027 plants this; no view offers "fill my
  basket with the usual".
- **Seasons.** Treats and toys before Christmas, grooming and flea
  products in summer. ADR 0027 leaves seasonality out; Demand's
  seasonality panel and Price's sweet spots are empty without it.
- **One signal, many views.** Ratings, reviews and discounts exist but
  only feed Feedback and Churn. In a real shop they shape
  recommendations, search ranking and analytics alike.

This ADR extends ADR 0027 rather than replacing it. 0027's lifecycle
(time order, staples, kits, durables) is the base; this adds the stories
on top, plus the views that show them.

## Decision

### Data: six planted effects, each with a check

Each effect is planted in `data/generate_fixtures.py` (on top of the
lifecycle branch) and pre-registered here with the check that shows Aito
recovers it. A check that fails means the effect is too weak or the
query is wrong; it is not tuned until it passes.

| # | Effect | Planted as | Check (`./do aito-check` or an eval script) |
|---|---|---|---|
| 1 | **Narrated personas** | 6–8 personas with a one-line story and hard rules: grain-free only, a senior dog, a new hamster owner, a budget multi-pet home, a cat with a sensitive stomach | `_recommend` top 10 for each persona breaks none of its rules; a rule-blind baseline breaks some |
| 2 | **Guided kit** | Per pet type, an ordered add-on list with P(next \| owned); a new owner walks it over weeks | Next-item hit rate @3 beats "most popular for this pet type" (paired CI) |
| 3 | **Routine** | 0027's staples (re-buy ~51 % of orders) | Next-basket prediction beats popularity; a shuffled-history control falls to popularity |
| 4 | **Seasons** | December ×1.8 on treats and toys, June–August ×1.6 on grooming and flea | `_relate` season × category: interval excludes 1 for the planted cells; Demand's panel non-empty |
| 5 | **Ratings matter** | Low-rated products are re-bought less and converted less from impressions | `_predict purchased` with rating evidence beats the base rate on log-loss |
| 6 | **Basket context** | Impressions carry the basket's categories, and purchase odds depend on them (bedding converts better with a cage in the basket) | The same search query with two baskets gives different top 5s, in the planted direction |

New columns are in the **initial schema**, never added in place:
columns added with v2 `PUT /schema/{table}/{column}` currently report
type `Unknown` and are modelled as categorical (td-20261012085637124211).

### Views: three new, three improved

- **New: "What's next for your pet"** (the guided kit). Pick a pet and
  what you already own; Aito ranks the next items with why
  ("customers with a cage and a water bottle buy bedding next"). From an
  empty start it walks a new hamster owner through the kit.
- **New: "Your usual basket"** (routine). For a persona, prefill a
  basket with the staples Aito predicts they're due for, each with its
  probability and when they last bought it.
- **Improved: Smart Search.** Persona chips with their story, and a
  basket: the same query ranks differently for "Grain-free Greta" with
  a puppy kit in her basket than for "Budget Bob".
- **Improved: For You** shows the persona's rules being kept.
- **Improved: Demand and Price** get their seasonality and sweet-spot
  cards back from effect 4.
- **Improved: Churn** can add event-driven causes later (a stock-out,
  a price rise, a bad review); kept out of this ADR.

## Aito usage

In the cheatsheet already: `_recommend` with a goal, `_predict`, field
`_relate`, Text `$match` context, the time-split `_evaluate`.

Not in the cheatsheet. Each is probed live and written up before any
view uses it, per CLAUDE.md:

1. **A user's own population**: a nested `from` scoping a query to one
   customer's history. The grocery demo uses it for autofill. Its notes
   say a nested `from` that matches no rows answers 400.
2. **Multi-label prediction for a basket**: a non-exclusive `_predict`
   that returns each staple's own probability, not one choice among them.
3. **`_recommend` conditioned on basket context** in impressions.

## Acceptance criteria

- Each of the six checks above passes on a test env loaded with the new
  data before shared master is touched.
- A user can open "What's next for your pet", pick a hamster with a
  cage, and see bedding or a water bottle in the top 3, with why.
- A user can open "Your usual basket" for a persona and see their
  staples prefilled, each with a probability.
- In Smart Search, the same query gives a different top 5 for two
  personas with different baskets, and the persona's story is on screen.
- No view shows an empty card on the new data, or the card says why.

## Demo impact

`docs/demo-script.md` gains a guided-kit beat ("I just got a hamster")
and a routine beat ("fill my usual basket"). The Smart Search beat uses
the new personas. The existing beats stay; their numbers change, and
tests that pin today's signals are updated with the reason.

## Out of scope

- Event-driven churn (stock-outs, price rises, late deliveries): its
  own follow-up.
- New products or categories, beyond what the kits need.
- Real customer data.

## Consequences

**Good:** the demo shows what a pet shop actually sells on (bundles,
routines, seasons) and personalisation a viewer can see.

**Bad:**
- A full reload of shared: env → `_migrate` → promote (ADR 0025), at
  night, by Antti. Every view's numbers change.
- The 2.11.4 `_delete` bug means the reload goes through a fresh env,
  not in-place deletes.
- More rows in `impressions`, the largest table; size is measured on the
  test env first (migrations have run out of memory on shared).

## Plan

1. Rebase `feat/lifecycle-data` onto main; add effects 1, 4, 5 and 6.
2. Load a test env; run the six checks; record results here.
3. Probe the three new query patterns; cheatsheet entries.
4. Build the two new views and the Smart Search changes, each its own PR.
5. Antti reloads shared at night; precompute; deploy.
