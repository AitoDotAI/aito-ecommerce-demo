# Personalised search: pre-registration (ADR 0037 §3)

**Fixed:** 2026-10-24, before any Aito ranking was scored.
**Run by:** `./do evidence personalised-search` (reads only), on env `observable`.
**Result:** `data/evidence/personalised-search.json`, rendered at `/evidence/personalised-search`.

This file fixes the design. ADR 0037 §3 (as revised on 2026-10-24) is the
source; where the ADR leaves a choice open, the choice is made here, before
the run, with its reason. A change after a result is seen is an amendment
at the end of this file, dated, with its reason.

**What was seen before this was written.** The probe below (query shapes,
the BM25 agreement, the timing). And one offline sanity check of the code,
with no Aito ranking in it: over all 3,030 sessions, the generator's
ranking had hit@10 0.768 and the Python BM25 0.561. Nothing below was
chosen with those numbers in mind; they are stated so a reader knows.

## The data

The release's env `observable` (ADR 0033), whose row counts match
`data/release-env.json` (117,026 impressions, 12,662 contexts). The
sessions are read from the committed fixtures and the regenerated
`data/impressions.json`, which `scored_sessions()` checks against the
release's count before scoring.

- 5,024 search sessions; 3,039 of them with a purchase.
- **Scored:** those 3,039 less the 9 that belong to the three hand-curated
  personas (CUST-00001..3): **3,030 sessions**.
- **A hit** is any product bought in that session (1 to 8 per session).
- **Prior orders:** the shopper's orders in months before the session's
  month (the generator's own "earlier orders"). Slices 0 (814 sessions),
  1–2 (1,197), 3–5 (638), 6+ (381).

## Held out

Every ranking that reads the impressions reads them through
`{"from": "impressions", "where": {"$not": {"context": <session>}}}`, as
`scripts/shop_query_sweep.py` does. The probe checked that the session has
0 rows inside its own `from`. `products` holds no session data, so the name
search is not held out (and is shared by every session with the same words).

## The six rankings

Each ranks the whole catalogue, or the part of it a ranking can reach.

| Ranking | Exactly what runs |
|---|---|
| **BM25** | `_search products` ordered by `{"$similarity": {"name": q}, "theta": 4.0}`, the products with `$score > 1` (a query word matched), ties by SKU. Smart Search's left column and the Shop's step 1. |
| **BM25, reference** | `src/personalised_search/bm25.py`: Okapi BM25, k1 = 1.2, b = 0.75, Lucene's IDF, lower-cased letter-and-digit tokens of the name; products scoring > 0, ties by SKU. |
| **Aito, the Shop's search** (primary) | `src/shop_search.py` with the session for the persona: step 1 as BM25; step 2 the grid's `_recommend impressions … goal {purchased: true}`, `where` = the household's declared pets, the session's month and its cart as words (`shop_context.shopper_where`), `just_bought: false`, the household's diet rule as a filter, `product_sku $or` the name matches less the cart; ranked by `$p × exp(4·bm25)`. The top 12 then get the Shop's just-bought re-ask (a `_batch` of `_predict purchased` with `just_bought: true` for products in the last order) and are re-sorted, as the page does. The cart is the session's basket (`contexts.basket`), as the shop sweep treats it. |
| **Aito, with the shopper's history** | `search_service.predictive_blend_body` for the session's shopper: `_search` from the held-out impressions, `get product_sku`, `where {context.customer: <id>}`, ordered by `$multiply [$p{purchased}, $similarity name θ 4.0]`, top 100. |
| **Household only** | The Shop's step-2 `$p` (same call, same candidates), ordered by `$p` alone, without the text lift. **Choice made here:** the ADR's "the grid's query, restricted" is read as restricted to the products the words name, so this ranking keeps the words' candidate set and drops only their ordering. It asks how much the household's `$p` orders the matches on its own. |
| **Generator's ranking** (ceiling estimate) | `src/personalised_search/generator_ranking.py`: the products the session's phrase could have come from (`shoppers.query_phrases`, on sale that month: exactly the generator's pool for that session), ordered by the weight `gen_impressions` gives each for this shopper, computed with the generator's own functions from the answer key (segment, pet size, diet rule, lifestyle, health focus, treat affinity, brand loyalty, favourite brands). |

θ = 4.0 is the shipped `TEXT_THETA`; nothing is re-tuned on this set.

**The ceiling is an estimate, not a bound.** The generator knows which
phrase it drew and from which pool it showed products; the purchase was then
drawn from what was shown, through the funnel, not from this weight. A
ranking can beat it in a slice by chance, and the page says so.

## Metrics

- **Primary: hit@10**: 1 if a product bought in the session is in the top 10.
- **Secondary: MRR**: the mean of 1 / (the rank of the first bought
  product), 0 when none is in the top 100 (`DEPTH`; the history form is
  asked for 100).
- Both per ranking, for all sessions and per slice, with a 95 % normal
  interval over sessions (mean ± 1.96 · SE, as ADR 0036).

## The three comparisons

Per slice and for all sessions, hit@10, paired session by session, with a
95 % normal interval of the per-session difference:

1. **the Shop's search − BM25**;
2. **the history form − the Shop's search**;
3. **the generator − the best Aito ranking**, where the best Aito ranking is
   the one of the Shop's search, the history form and household only with
   the highest hit@10 point estimate in that slice (a tie goes to the
   Shop's search, then the history form).

## Wording (enforced in `src/personalised_search/wording.py`, with tests)

- An interval that spans 0 is "a tie".
- A lead ("is ahead of") is stated only when the interval excludes 0, in
  that direction; the code refuses any other sentence with lead words.
- A slice under 30 sessions is "too few to read" (none is expected: the
  smallest has 381).
- The page's synthetic-data sentence is above the first number.
- The Shop's search reads the household, not the history, so it isn't
  expected to rise with history; the history form is. Whether the history
  form leads the Shop's search in any slice is answered by comparison 2,
  not claimed.

## The probe (run before this was written)

`./do evidence personalised-search --probe`, 2026-10-24, Aito 2.11.8, env
`observable`:

1. A session's rows inside its held-out `from`: 0.
2. Both search shapes answer with the nested `from`: the Shop's `_recommend`
   returned `$p` in [0, 1] for every allowed name match (e.g. 183 of 183 for
   "beef dog"; 74 of 385 for "dog food" in a `sensitive` household, the rule
   filter at work); the just-bought re-ask, a `_batch` of `_predict
   purchased` with the nested `from`, returned a `true` probability for each
   product asked; the history form returned 50 distinct products of 50
   asked (the timing step asked for 100).
3. `$similarity` against the Python BM25 on 20 seeded queries: the same
   products matched on every query, the same top 10 on 20 of 20, Pearson r
   ≥ 0.9947 between `ln($score)` at θ = 1 and the Python score, and
   `ln($score)` ≈ 0.99 × the Python score. The pre-set bar (≥ 18 of 20 same
   top 10 and r ≥ 0.99 on each) is met, so **the left column is named
   BM25**.
4. Timing: 1.60 s per session at 4 concurrent requests, 1.34 h for 3,030.
   Under the 2-hour rule, so **the full set is scored; no subsample**.

## Known limits, stated before the run

- In 62 sessions a product bought was also in the session's cart; in 14 all
  of them were. The Shop's search leaves cart items out, as shipped, so it
  cannot hit those; BM25 and the history form can.
- Purchases are drawn from what the generator showed, and it showed only
  products of the drawn phrase's pool. Every ranking is scored on the same
  purchases.
- Synthetic data with planted effects: this tests whether Aito finds the
  shopper the generator planted, not how large personalisation is in a real
  shop.

## The run (recorded after it, not part of the design)

2026-10-24, Aito 2.11.8, env `observable`, all 3,030 sessions, no subsample.
It took about 2 h 10 min, not the 1.34 h the timing step estimated: a
second read-only run (`./do search-eval`) shared the instance for most of
it, and many calls paid this machine's ~5 s DNS lookups. The design held
the full set, chosen on the timed estimate before the run, so no subsample
was drawn. Results: `data/evidence/personalised-search.json`.

## Amendments

### Amendment 1 (2026-10-24, before any run on it): re-registered for data release 2, env `release2`

Data release 2 (ADRs 0038–0040, 0044, 0045) is loaded in env `release2`
(`data/release-env.json`: 96,028 impressions, 61,484 contexts). The design
above was fixed on release 1. Three of its parts don't carry over, so they
are fixed again here, before any ranking is scored on release 2. Everything
not named here stands: the six rankings, θ = 4.0, hit@10 and MRR, the three
comparisons, the wording and the slices.

**What was seen before this was written.**
- Counts from the local fixtures (below).
- The probes of data release 2 (`docs/aito-cheatsheet.md`, "Data release 2").
- The no-profile Shop sweep's interim scores over 306 of its 1,400
  sessions (`actionable-states-prereg.md`). The sweep, not this benchmark,
  decides which evidence the Shop uses for a shopper without a pet profile,
  and part 3 takes whatever it decides.

No ranking of this benchmark was run on `release2`.

1. **Hits are purchases from the search results.**
   - Since ADR 0045 a session shows two parts of a page. `buy_again` holds
     what the household came for, bought 80–90 % of the time whatever was
     searched. `list` is the shop's ranked results.
   - 1,692 of the 1,791 search sessions with a purchase bought something on
     `buy_again`.
   - A hit is now a product **purchased on `placement: list`** in the
     session. A scored session is a search session with at least one such
     purchase, personas left out: **1,150 sessions** (slices 0: 335, 1–2:
     431, 3–5: 246, 6+: 138).
   - Every product bought lies in the generator's pool for its phrase (0 of
     1,150 outside it).
2. **The cart is empty: the search is scored on arrival.**
   - Since ADR 0045 a session's `basket` is its own order. 1,692 sessions
     hold a bought SKU in it.
   - Used as the Shop's cart, the basket would remove the answer from the
     candidates. As context words, it would carry the answer.
   - The "known limit" of 62 sessions on release 1 would now be nearly every
     session. So no ranking gets a cart.
3. **A shopper without a pet profile (698 of the 1,150).**
   - The Shop's search reads the household's declared pets
     (`context.customer.pets`), and these shoppers declared none.
   - For them, the Shop's search and household-only rankings take the
     evidence the no-profile sweep chooses for "Picked for you", by its own
     registered rule: `NO_PROFILE_EVIDENCE` in
     `src/personalised_search/rankings.py`. Until the sweep concludes, that is
     `None`, a session without a profile raises, and the benchmark doesn't run.
   - It is evidence only. The search has no pet filter, as shipped, so a
     gift for another pet can be found.
   - A shopper with a declared profile keeps the shipped `where`: declared
     pets and the month.
   - For 196 of the 698 there is no earlier order, so no `pets_from_orders`
     yet. Their evidence is the month alone, plus identity if the chosen
     form holds it.
4. **The ceiling** is unchanged: the generator's `_browse_weights` for the
   phrase's pool. Since ADR 0045 the generator also multiplies each weight
   by the shop's merchandising factor (offers, new products, stars), which
   the ceiling doesn't read. It stays an estimate.
5. **Size and timing.** 1,150 sessions is fewer than the 1,400 of a
   subsample, so **the full set is scored**. At release 1's 1.6 s a session
   (4 at a time), that is about 31 minutes.
6. **Tests.** `tests/test_personalised_search_sessions.py` holds these
   counts for env `release2`.
