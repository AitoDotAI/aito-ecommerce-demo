# Verification — Shop search, alternatives and reasons (ADR 0031, amendment of 2026-10-17)

`./do verify` isn't wired to an adversary agent yet, so this pass was run
by hand on 2026-10-17: a read-only backend (`PUBLIC_DEMO=1`, port 8602) on
master's ADR 0030 data, the static export, and Playwright at 1440 × 1000
and 390 × 844. It tried to break the feature, not to confirm it.

## Acceptance criteria

| Criterion | Result |
|---|---|
| "dental" in the Shop gives only name matches, ranked for the shopper, with the same cart and rule | Pass: `tests/test_shop_search.py`; live, Sofia's "bottle" with a cage in the cart puts the PetNord bottle (45 %, "Goes with your cart ×4.5") first |
| A query no name matches says so and shows nothing | Pass: "zzqx", "hidout", "$or {}", "koiranruoka" all answer `text_matched: false`; the page says "No product name holds a word of …" |
| Every card shows up to three Aito reasons, offers and stars only as facts | Pass: teal chips for reasons, grey/green for facts; 12 of 12 cards had reasons in Sofia's (with a cage), Janne's and Helena's grids, 10 of 12 in Janne's "food" search (the other two have no reason of at least ×1.15, or no impressions of their own, see below) |
| An opened product shows details, alternatives for this shopper, and same-basket products | Pass: a water bottle's alternatives are three bottles (2 %, 1 %, 0 %); same-basket shows cages 54.8× (23 of 59 orders) |

## Edge cases tried (API, live)

| Case | Result |
|---|---|
| Janne (grain-free) searches "food", "chicken", "grain free" | Only grain-free dog and cat food (`test_shop_search_keeps_the_household_rule`) |
| The cart holds the only match ("exercise wheel" with the wheel in the cart) | 200, matched, no items; the page says none can be offered |
| 500-character query | 200 in 0.96 s |
| Empty or whitespace query | 400 "Search needs at least one word" |
| Unknown shopper, unknown or duplicate cart SKU, unknown product | 404 / 404 / 400 / 404, each with its message |
| Month `2026-13` | 422 (pattern) |
| Earliest month, 2024-05 | 200; no just-bought re-ask (no earlier orders) |
| Drawer for a product that is in the cart | 200; the alternatives leave out the product and the cart |
| Janne opens a rule-breaking cat food | Alternatives are grain-free cat food only |
| Aquarium product (few impressions) | 200, four alternatives |

Latency on the shared instance: search 0.3–1.0 s, drawer 0.8–0.9 s, grid
0.9–1.0 s. No page errors in either viewport.

## Found and fixed during the pass

- Janne's "food" returned nothing: only the top 60 name matches were
  ranked, and the rule filtered out all of them. Now every name match is
  ranked (`$p` only), and the top 12 are asked for reasons.
- A product with few impressions has no own lift in `$why` (only
  `hitLinkPropositionLift`); the parser raised. It now shows no reasons,
  documented in `src/shop_reasons.py` and the cheatsheet. More than one
  own lift still raises.
- A water bottle's alternatives were hideouts and cages ("accessories"
  is broad); a kit item's alternatives now also match its type by name.
- On a phone the results sat below the cart and suggestions; when
  searching they now come first.
- "ranked for Sofia Kallioby Aito's…": the compiler dropped the space
  after `{shopperName}` in wrapped JSX text; the caption is a template
  string now.

## Known limits (not failures)

- Misspellings find nothing ("hidout"): the name must hold a query word.
  The page says so rather than show unrelated products.
- Same-basket pairs come from all orders, so a grain-free shopper's
  drawer can list a non-grain-free food as often bought together. It is
  labelled "From all orders".
- Offers and ratings are facts, not reasons, until a data change records
  offers on impressions (proposed in the ADR amendment).
