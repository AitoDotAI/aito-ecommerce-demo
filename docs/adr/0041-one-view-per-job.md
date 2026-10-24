# ADR 0041: One view per job — the site's structure

**Status:** Accepted (2026-10-24, Antti: "review, fix and merge all on green")
**Date:** 2026-10-24
**Deciders:** Antti

## Context

The app grew one view per Aito capability: Smart Search, For You, Bought
Together, Cart Completion, Pattern Explorer, Basket Rules, and so on. Then
the Shop (ADRs 0031, 0033) put the shopper's side into one place, and
Shop analytics put the owner's patterns into one view with intervals.
The older views stayed. A review of the site (2026-10-24) found:

- **The Shop already does what four shopper views do, with better
  queries.** For You and Smart Search personalise by the customer's id
  (`context.customer`). ADR 0033's held-out sweep found that form ties on
  hit@10 and calibrates worse than the Shop's declared-pets form, and the
  Shop dropped it. Demo beats 2 and 3 still show it.
- **Six views send the same basket `_relate`:** Dashboard, Bought
  Together, Pattern Explorer, Basket Rules, Shop analytics and Cart
  Completion. All show "dog dry food → dental treats 2.66×"; only Shop
  analytics gives its interval and counts.
- **Four views look at one product:** Product Insights, Price's
  drill-down and what-if, and ADR 0038's planned product manager's view.
- **Accuracy numbers sit inside demo views:** Churn's 96 % vs 65 %,
  Demand, Evaluation, and a static "98 %" badge. ADR 0037 keeps them in
  Evidence.
- **The app has one cross-link.** A product on the Shop can't be opened
  from the owner's side.

ADRs 0038–0040 add three owner views. Added to today's set, the site would
have 26 entries, many asking the same question.

## Decision

### Principles

- **One job per view, one view per job.** Each function below lands in
  exactly one view.
- **Sections follow the person, not the endpoint:** the shopper, the
  owner running the shop, the operator automating chores, the evaluator
  asking "how well?", the developer. The Aito panel on every view already
  teaches the endpoint.
- **Objects link across views.** A product, a shopper or a pattern opens
  the same detail wherever it appears.
- **No accuracy numbers outside Evidence** (ADR 0037).

### The sitemap

```
360° INTELLIGENT ECOMMERCE
  Shop            Shop: Buy again · Next for their kit · Picked for you,
                  search, cart, product drawer
  Run the shop    Overview · Patterns · Product · Supply ·
                  Acquisition (0040) · Retention · Reviews & NPS (0039)
  Operate         Product filling · Review triage
EVIDENCE          Index · Business reorders (real, 0034) ·
                  Personalised search · Search relevance · Model checks
FOR DEVELOPERS    Query patterns: one minimal, runnable call per endpoint
```

17 entries, against 19 shown and 4 hidden today, with ADRs 0038–0040's
views included.

### Each view's one job

| View | For | The question it answers |
|---|---|---|
| Shop | shopper | What should I buy now, for my pets, on this visit? |
| Overview | owner | How is the shop doing, and where should I look? One headline per owner view, each a link |
| Patterns | owner, analyst | What goes with a click, a purchase, a basket, a search word, a group? |
| Product | product manager | What will this product do this month, why, and what if I change its price, discount, label or stock? For whom? |
| Supply | buyer, ops | What do I reorder, what's overstocked, and what markdown clears it? |
| Acquisition | marketer | Which sources bring visitors who buy and stay? |
| Retention | CRM | Who is about to leave, why, and what offer brings them back? |
| Reviews & NPS | owner, CX | What do reviews and experiences do to clicks, sales, NPS, churn, demand and price? |
| Product filling | catalogue editor | Fill this product's missing fields |
| Review triage | support | Route this review |
| Evidence pages | evaluator | How well does it work, against what baseline? |
| Query patterns | developer | What does each Aito endpoint look like, minimally? |

### Where each current function goes

| Today | Goes to |
|---|---|
| Shop | Shop, unchanged |
| Smart Search's side-by-side (text only vs personalised) | Evidence › Personalised search, as the live illustration above the benchmark |
| For You's persona grid (`_recommend` with `context.customer`) | Query patterns › `_recommend`, labelled as the minimal form |
| Bought Together | per category: Patterns › Baskets; per product: the Shop drawer's "often in the same basket" |
| Cart Completion (hidden) | dropped: the Shop's cart re-ranks "Picked for you" |
| Basket Rules, Pattern Explorer | Patterns › Baskets: confidence and support columns, an anchor filter |
| Shop analytics | Patterns (renamed) |
| Dashboard, Purchase Analytics | Overview; Purchase Analytics' category mix is already in Patterns › Who buys what |
| Product Insights | Product › History |
| Price's demand curve and what-if; the discount-band what-if | Product › What if |
| Price's fair-band table | Supply, as a price column with its outlier flag |
| Price's sweet-spot block | dropped: nothing passes its own filter on today's data |
| Demand, Inventory, Markdown | Supply (one forecast; markdown is an action on an overstock row) |
| Demand's and Churn's accuracy blocks, Evaluation | Evidence › Model checks |
| Churn, Win-back | Retention (the win-back offer is an action on an at-risk row) |
| Feedback | Review triage, without its "churn risk" field (reversed causality, ADR 0039) |
| Product filling | Product filling, without the static "98 %" badge |
| ADR 0034's Business reorders | Evidence › Business reorders |

Old routes redirect to their new home, so links in posts and the README
keep working.

### Moving between views

| From | To |
|---|---|
| A Shop card or drawer: "Owner view →" | Product, same product and month |
| A Shop reason ("goes with your cart") | Patterns › Baskets, that pair |
| Product › for whom: "See it as this shopper →" | the Shop, as a shopper from that band |
| Product › low stock / stars | Supply, that row / Reviews & NPS, that product |
| A product in Patterns | Product |
| An Overview headline | its owner view |
| Any 360° view: "How well? →" | its Evidence page |
| Any Aito panel: "Minimal form →" | Query patterns, that endpoint |

### Phases

1. **With today's data:** the sections and names; Patterns, Product
   (History plus both what-ifs), Supply, Retention and Overview as merges;
   the moves to Evidence and Query patterns; the cross-links; the
   redirects; the stale copy found by the review. One PR per merged view.
2. **With ADRs 0038–0040's release:** Product's levers, Reviews & NPS and
   Acquisition slot into their places.

## Aito usage

No new query shapes. Each merged view keeps the queries of the views it
absorbs. Where two views sent the same query, the merged view sends it
once. Patterns keeps Shop analytics' intervals and significance bar for
the rows it takes over from Basket Rules and Pattern Explorer.

## Acceptance criteria

- [ ] The sidebar shows the sections and entries above, and nothing
      else.
- [ ] Every function in the table above is reachable in its new view,
      and in no other.
- [ ] Each old route redirects to its new home.
- [ ] A user can go from a Shop card to Product for the same product and
      month, and back to the Shop as a shopper from Product's "for whom".
- [ ] No 360° view shows an accuracy number; each links to its Evidence
      page.
- [ ] `docs/demo-script.md` follows the new path, and every number it
      quotes matches the live view.

## Demo impact

All five demo moments move. The script becomes **Shop → Product →
Patterns → Evidence**:
- **Shop:** Maija and Janne search "food" and get different grids; "food
  for an old dog" finds dog food. This replaces beats 2 and 3.
- **Product:** the same product, from the owner's side: its history, and
  what a discount would do.
- **Patterns:** dog dry food → dental treats 2.66× [2.34, 3.03], the
  basket pattern behind the Shop's cart suggestions. This replaces
  beat 4.
- **Evidence:** "for how well, here it is", ending on real data. This
  replaces beat 6.
- Product filling's beat stays.

The Quick-recovery rows and the numbers the script quotes are rewritten
from the live views.

## Out of scope

- New Aito capabilities; this ADR only moves and merges.
- A visual redesign of the views themselves.
- Mobile layout changes beyond keeping today's.

## Consequences

**Good:**
- A reader meets each idea once, in its best-measured form.
- The owner's side reads as one tool, linked by product and shopper.
- ADRs 0038–0040 add three views without adding duplicates.

**Bad:**
- A large change to a working demo. The phases keep main demo-runnable
  after each PR.
- Live checks for moved queries must follow them: three Smart Search, two
  For You and one Basket Rules test in `tests/test_aito_check.py`. Each
  is kept where its query lives on, and dropped otherwise.
- External links to old routes rely on the redirects.

## Notes

The full review, with every view's queries compared and each demo beat a
move breaks: `docs/notes/2026-10-24-site-review.md`.
