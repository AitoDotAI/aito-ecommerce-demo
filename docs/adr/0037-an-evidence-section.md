# ADR 0037: An evidence section, kept apart from the demo

**Status:** Accepted (2026-10-24, Antti: "review, fix and merge all on green")
**Date:** 2026-10-24
**Deciders:** Antti

## Context

The app now does two jobs that pull against each other:

- **The demo, "360° intelligent ecommerce":** the pet shop and the owner's
  views. It shows how Aito answers a shop's questions. Its data is
  synthetic with planted effects, so its copy makes no accuracy claims.
- **Evidence:** a reader evaluating Aito also asks "how well does it work,
  against what?" That needs a method, baselines, intervals and a
  reproducible run. It doesn't belong inside the demo's screens.

Evidence already exists, but it's scattered:
- ADR 0034's Business reorders page, on real data (UCI Online Retail II),
  with a claim cleared by Aito core;
- ADR 0036's backtest tool, a script and a report;
- the judged search evaluation (`./do search-eval`, ADR 0026), as a
  Markdown report.

That report has a stated gap: its relevance labels ignore the shopper, so
"it cannot see personalisation". The demo's headline search moment is
personalisation, and nothing measures it.

Benchmarks on synthetic data are tempting and easy to get wrong. On data
where we planted the shoppers' preferences, a personalised ranking beating
a text-only one is true by construction. Read as "Aito beats BM25", the
number is circular. Synthetic data offers something real data can't,
though: **the truth is known.** The generator holds each shopper's hidden
traits, so a benchmark can ask how much of the planted signal Aito
recovers, measured against the generator's own ranking as a ceiling, and
from how much history.

## Decision

### 1. Two sections

- **360° intelligent ecommerce:** the shop and the owner's views, as
  today. No accuracy numbers. It may link to an evidence page.
- **Evidence:** an index page, then one page per benchmark. Each is
  marked **Real data** or **Synthetic data** on the index and on its page.

The first entries:

| Entry | Data | Source |
|---|---|---|
| A business buyer's next order | Real (UCI) | ADR 0034's page, moved here from beside the shop |
| Personalised search | Synthetic | this ADR, §3 |
| Search text relevance | Synthetic | `./do search-eval` (ADR 0026), the existing report rendered as a page |

ADR 0036's backtest stays a script; its UCI table can appear on the UCI
page once the live run reproduces it.

### 2. Rules for every evidence page

- **What's measured:** the method, the baselines, n, the metric, paired
  95 % intervals, the run's date, the Aito version, and links to the
  script and the ADR.
- **Numbers come from committed result files** (`data/evidence/*.json`),
  written by a `./do` command and re-runnable by any reader. A page never
  runs a benchmark live.
- **Wording, as in ADR 0036:**
  - a difference whose interval spans 0 is "a tie";
  - no sentence claims a win outside the intervals that exclude 0.
- **Synthetic pages carry, above the first number:** "Synthetic data with
  planted effects. This tests whether Aito finds the effects, not how
  large they are in a real shop."
- Real-data claims are worded only as cleared (ADR 0034's rules).

### 3. Personalised search: how much of the shopper does Aito recover?

**The data.** The generator's search sessions: each has the shopper, a
query (S7: drawn from a product the shopper is drawn to, using words from
its name) and what was shown, clicked and bought. On the current
generation:
- 5,024 search sessions;
- 3,039 of them with a purchase.

These are rows a shop observes (ADR 0033), so the labels are purchases,
not judgements.

**Scored sessions:** every search session with a purchase, except the
three hand-curated personas. A hit is any product bought in that session.

**Held out:** each session is scored with Aito reading everything except
that session, the nested-`from` pattern of the shop sweeps
(`scripts/shop_query_sweep.py`).

**The rankings**, each over the whole catalogue:

| Ranking | What it is |
|---|---|
| BM25 | Smart Search's left column: `_search products` ordered by `$similarity` over the name |
| BM25, reference | a plain Okapi BM25 in Python (k1 = 1.2, b = 0.75, over the same names), to show the left column is a standard BM25 |
| **Aito, the Shop's search** (primary) | `src/shop_search.py`, as shipped: the products the words name (`_search products`, `$similarity`), then the grid's `_recommend` restricted to them, with the household's declared pets, the month and the cart, and the household's rule as a filter; ranked by `$p` × the text lift at the shipped θ (no re-tuning on this set) |
| Aito, with the shopper's history | Smart Search's right column: `$multiply [$p{purchased}, $similarity name]` with `context.customer`, at the shipped θ. It's the form the Shop dropped (ADR 0033, R1/R2); here it answers whether the shopper's own history adds anything over the household |
| Household only | the Shop search's `$p` alone, with no text lift: how much the household explains without the words |
| Generator's ranking | the generator's own weight for this shopper and product, restricted to products the query's words could have come from |

The generator's ranking is the ceiling estimate. The purchase is drawn
from what was shown, not from this weight, so it isn't a strict upper
bound; the page says so. It needs the generator's per-shopper inputs
(favourite brands, pet size, diet rule). Those go into the answer key,
which is never loaded into Aito. The loaded tables must stay
byte-identical, and a test checks it.

**Metrics:**
- **Primary:** hit@10.
- **Secondary:** MRR.
- **Slices:** the shopper's orders before the session: 0, 1–2, 3–5, 6+.
  The page shows each ranking per slice, with the generator's ranking as
  the ceiling. The Shop's search reads the household, not the history, so
  it isn't expected to rise with history; the history form is. Whether
  the history form beats the Shop's search in any slice is a question the
  run answers, not a claim.
- **Intervals:** paired 95 % over sessions, per slice, for:
  - the Shop's search − BM25;
  - the history form − the Shop's search;
  - the generator − the best Aito ranking.
  
  A slice under 30 sessions is "too few to read".

The design is fixed in this ADR before any run. A change after a result
is seen is an amendment, dated, with its reason.

## Aito usage

| Query | Status |
|---|---|
| `_search products`, `$similarity` over name | shipped (ADR 0026) |
| The Shop's search (`_search products`, then the grid's `_recommend` over those products) | shipped (ADR 0031, amendment of 2026-10-17) |
| Smart Search's `$multiply [$p{purchased}, $similarity]` | shipped (ADR 0026) |
| Each, with a nested `from` that excludes the session | the sweeps' pattern; probed again on both search shapes before the run |
| The Shop search's `$p` alone, no text lift | the grid's query, restricted; probed before use |

**Before building on it:** a probe of how `$similarity` scores the names
(tokens, stemming, length normalisation), compared with the Python BM25
on 20 queries. If they disagree, that's reported, not hidden: the page
then names the left column "Aito's text similarity", not BM25.

**Cost:** about 3,000 sessions × 4 Aito queries (the Shop's search is
two), on the release data's env, outside 08–10 Helsinki.

**Revised 2026-10-24, before any run:** the primary Aito ranking is the
Shop's search, not Smart Search's. The site review behind ADR 0041 found
that the benchmark would otherwise measure a query the Shop doesn't run.
Smart Search's form stays as the history comparison.

## Acceptance criteria

- [ ] The app's navigation has two sections, 360° intelligent ecommerce
      and Evidence. Business reorders sits under Evidence.
- [ ] The Evidence index lists each entry with its Real or Synthetic
      mark and a one-line result worded by the rules in §2.
- [ ] A user can open Personalised search and see hit@10 per history
      slice for the six rankings, with intervals. The synthetic-data
      sentence is above the first number.
- [ ] Every number on an evidence page comes from a committed file in
      `data/evidence/`. `./do evidence <entry>` rewrites it.
- [ ] A difference whose interval spans 0 is shown as "a tie".
- [ ] No screen in 360° intelligent ecommerce shows an accuracy number.
- [ ] The answer key's new fields leave the loaded tables byte-identical.

## Demo impact

`docs/demo-script.md` keeps the shop walkthrough. Its closing beat
becomes: "That's how it works. For how well, on real data and against
baselines, here's the evidence section." The UCI beat moves there.

## Out of scope

- A benchmark run from the browser, or on a visitor's data. ADR 0036's
  backtest stays a script.
- Re-tuning Smart Search on this set. If the result suggests it, that's a
  new ADR with an out-of-sample choice, as in the search eval.
- Evidence entries for the other demo views (recommendations, churn,
  demand). Each would be its own ADR with its own pre-registered design.
- Comparisons with other vendors.

## Consequences

**Good:**
- The demo can stay free of accuracy claims without hiding the evidence.
- Real and synthetic results can't be confused: each is marked, and each
  synthetic page states what it can't prove.
- The personalisation question the search eval couldn't answer gets
  answered, with a ceiling that real data can't give.

**Bad:**
- One more section to keep current: each data release can change the
  synthetic results, so the release re-runs `./do evidence` (ADR 0035's
  precompute step is the natural place).
- A synthetic result can still be quoted out of context. The fixed
  sentence and the mark reduce that; they don't prevent it.

## Notes

- The search sessions and the generator's ranking depend on ADR 0030's
  generator. With ADR 0033's observable data (PR #64), the run uses that
  release.
- If BM25 and Aito tie at 0 history, as expected, the page says so: with
  no history, personalisation has nothing to read.
