# ADR 0034: A business buyer's next order, on real data (UCI Online Retail II)

**Status:** Accepted (2026-10-22, Antti: "do both")

## Context

Everything else in this demo runs on synthetic data with planted effects. That
shows how Aito works, but no number from it can be quoted. Aito's core team
benchmarked next-basket prediction on a real dataset, UCI Online Retail II: two
years of invoices from a UK online giftware wholesaler, many of whose
customers are themselves businesses. The result is cleared for use:

> For buyers with 1–2 earlier orders, Aito's top suggestion was in their next
> orders 31 % of the time, against 15 % for the strongest of five classical
> baselines (EASE).

A buyer's reorder is the B2B use case partners ask about (a draft of the next
order, ready before they ask). This ADR adds one page that shows it on that
data, with the benchmark's own query, so the number on the page is the
benchmarked one.

Source: Chen, D. (2012). Online Retail II [Dataset]. UCI Machine Learning
Repository. https://doi.org/10.24432/C5CG6D. Licence CC BY 4.0: attribution
required, commercial use permitted.

## Decision

A new page, **Business reorders**, in its own Aito env (`uci`), separate from
the pet shop.

**The data, as the benchmark prepared it**, so its results reproduce:
- Cleaning, as coded in the benchmark:
  - drop credit notes (invoice ids starting `C`), rows with no Customer ID
    (22 %, guest and till traffic, not a random sample) and non-positive
    quantities;
  - keep every StockCode, including `POST` and `M`;
  - an invoice's items are a set.
- Tables `customers`, `invoices` (with `month`) and `lines` (`code` as a
  String), exactly as the benchmark loaded them. Only invoices before
  **2011-09-01** are loaded: that is the benchmark's training data.
- Two more tables, kept out of the predicted path:
  - `products`: code, description, the last unit price in £; not linked from
    `lines`, so a link prior can't change the ranking;
  - `baskets`: one row per invoice, its codes as Text, for basket analysis.
- What each buyer actually ordered on or after 2011-09-01 is kept beside the
  app (not in Aito). The page uses it to show the outcome.

**The page:**
1. **Pick a buyer:** a short list of real customer ids, for buyers with
   1–2 earlier orders and for regular buyers. Customer ids only; UCI holds
   no names.
2. **Aito's draft of their next order:** the top 10 codes, with Aito's
   probability, the description and the last price in £. The draft's value
   is the sum of those prices at one unit each, and is labelled so.
3. **What they ordered next:** the draft's codes they actually bought after
   the cutoff are marked. The first suggestion's hit is the benchmark's
   measure.
4. **The claim,** worded as cleared (below), with the citation.
5. **Bought together:** pick a product, see what is bought with it.

Money is shown in £, as the data are; nothing is converted.

## Aito usage

| What | Query | Status |
|---|---|---|
| The draft order | `_predict` `{"from": "lines", "where": {"invoice.customer_id": id}, "predict": "code", "limit": 10}` | The benchmark's shape; byte-stable across the v2.11.9 candidates (dev3, 2026-10-21) |
| Bought together | `_relate` on `baskets`, `where {"codes": {"$match": code}}`, relating `codes` | `_relate` over a Text field is in the cheatsheet; probed on `uci` before use |
| Labels | `_search products` by code | plain search |

## Acceptance criteria

- A user can pick a buyer with 1–2 earlier orders and see Aito's draft of
  their next order, each line with its probability, description and £ price.
- When the buyer later ordered a drafted code, the page marks it. The first
  suggestion's mark matches the benchmark's hit@1 for that buyer
  (`benchmarks/ecommerce-reco/retail2/analysis.json`, aito-core 625867faca).
- The claim is worded exactly as cleared (below). The page cites UCI.
- `./do aito-check` on env `uci` reproduces the benchmark: Aito's hit@1 over
  the benchmark's buyers with 1–2 earlier orders is exactly 197 of 636
  (0.31), as in the benchmark's run: the query is deterministic.
- A user can pick a product and see what is bought with it, with lifts.

## The claim, as cleared

- **Say:** "For buyers with 1–2 earlier orders, Aito's top suggestion was in
  their next orders 31 % of the time, against 15 % for the strongest of five
  classical baselines."
- **Don't say:**
  - "the whole order was right" (it's the top suggestion: hit@1);
  - "beats every baseline": for buyers with 3 or more orders, Aito and the
    best classical baseline tie (paired test, n = 1,708). That's a tie, not
    a loss, and the page doesn't concede one;
  - anything about buyers with no history (there Aito equals popularity).
- **Overall:** 31.5 % vs 28.7 % for the strongest baseline.

## Demo impact

`docs/demo-script.md` gains a short beat after the pet shop: "Now real data.
This is a wholesaler's buyer with two earlier orders; here is the next order
Aito drafts, and here is what they actually ordered."

## Out of scope

- Churn on UCI. Core's churn benchmark (cleared: untuned Aito beats a
  recency rule, AUC 0.767 vs 0.726) can become a later page with core's
  (customer, cutoff) table.
- "Who was saved": UCI has no actions or control group.
- Telling businesses from consumers: the data doesn't mark them.
- Any claim about buyers with no history, or about discovering new products.
