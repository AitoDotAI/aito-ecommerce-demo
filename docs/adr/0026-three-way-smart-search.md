# ADR 0026: Smart Search as one three-way blend — text × meaning × purchase probability

**Status:** Proposed
**Date:** 2026-09-27
**Deciders:** Antti

## Context

Smart Search shows the same query side by side: a plain baseline on the
left, a predictive ranking for the chosen customer on the right. A
judged evaluation (`./do search-eval`, 60 queries in six groups, every
product graded from its attributes; report in
`docs/verification/search-eval.md`) measured both columns:

| | nDCG@10 | queries with no results |
|:--|--:|--:|
| Left: `_search name $match` | 0.293 | 70 % |
| Right: `_recommend` with a `name $match` candidate filter, any persona | 0.293 | 70 % |
| BM25 over the name (`$similarity`), not shipped | 0.599 | 0 % |

`$match` requires every query word in the product name. Natural
phrasing ("food for an old dog"), misspellings and Finnish/Swedish
queries return nothing, in **both** columns: the predictive column can
only reorder what the filter lets through. BM25 fixes most of that
(+0.306 nDCG@10, 95 % CI [+0.212, +0.409]), but it is still word
matching. Its weakest group is Finnish/Swedish, at 0.233.

Switching only the left column to BM25 would invert the demo: a
query would show ten sensible results on the left and nothing on the
"smart" right. Both columns have to change together.

## Aito usage

Aito v2 ranks by a product of probability lifts in one `orderBy`. That
is text relevance × semantic closeness × purchase probability in a
single query, with no candidate filter. The shape below is the one
the engine's own reference and booktest use
(`api-docs/content/vector-search-v2.md` §"The three-way blend",
`HybridSearchTest/threeWayBlend.md`, v2.10.3 and master):

```json
{
  "from": "impressions",
  "get": "product_sku",
  "where": {"customer_segment": "dog_owner", "customer_pet_size": "large"},
  "orderBy": {"$multiply": [
    {"$p": {"$context": {"purchased": true}}},
    {"$similarity": {"name": "food for an old dog"}, "theta": 0.33},
    {"$vectorIdf": {"vec": [0.013, -0.091, …]}, "theta": 0.87}
  ]},
  "select": ["sku", "name", "$p"],
  "limit": 10
}
```

- `$similarity` is BM25 as a lift, `exp(0.33·bm25)`. It is resolved on
  the link target (`products.name`).
- `$vectorIdf` is the self-calibrating vector lift `(1/p)^θ`, where `p`
  is how rare that cosine is among the candidates. The default θ
  carries across embedding models.
- `$p{$context: {purchased: true}}` is the probability that this
  customer context buys the product, learned from the `impressions`
  funnel. It is the same signal today's right column uses.
- Ranking depends only on the ratio of the two θs; the defaults are the
  starting point, and any tuning is judged on the harness.

**Not yet verified, and checked before any code builds on it** (prime
directive 3):

1. That persona context in `where` conditions `$p` in the `get` form, as
   `where` does in `_recommend` today. Check: the right column must
   still flip between Maija (cat) and Saara (large dog) for "food".
2. The query-time cost of `$p` over `impressions` inside `$multiply`.
   Today's `_recommend` runs at p50 2.4 s; the blend must not be slower.

Both get checked against a local engine first, with no shared write,
then read-only on shared.

## Decision

Ship in two steps, each measured on the harness before it merges.

### Step 1: text × purchase probability (no new dependency)

- **Left column:** `_search` ordered by `$similarity` over `name`
  (BM25). It stays the honest non-predictive baseline, now a real
  ranker.
- **Right column:** the blend above without the `$vectorIdf` part,
  `$p × $similarity`. The `name $match` filter goes.
- **Harness:** the right column is scored once per persona, next to
  BM25.

### Step 2: add meaning (vectors)

- **Embedding model:** `intfloat/multilingual-e5-small` (384
  dimensions). It is multilingual on purpose: the Finnish/Swedish group
  is where word matching fails. e5 expects `passage: ` before indexed
  text and `query: ` before queries.
- **What gets embedded: the product `name` only.** It is the same text
  the lexical arm reads. The relevance labels come from product
  attributes (pet, category, diet, brand), so embedding those
  attributes would hand the vector arm the answer key and inflate its
  score. In a real shop you would embed the full description; here the
  comparison has to be fair.
- **Product vectors** are computed offline by a `./do embed-products`
  step. They are stored in a `products.vec` column
  (`{"type": "Vector", "dimensions": 384, "similarity": "cosine"}`),
  with the model id and file hash written to
  `data/product_embeddings.meta.json`.
- **Query vectors** are computed in the backend with `onnxruntime`
  from the same model file. The file is pinned by SHA-256, and the
  backend **refuses to start** if its model id or hash differs from the
  one recorded for the product vectors. Mixed models produce vectors
  that look valid but aren't comparable, which is the silent failure
  this project rules out.
- **Why not Aito's column `embedder`:** it calls an external embedding
  endpoint (TEI, Ollama, OpenAI, Cohere). The demo would need another
  service running. In-process ONNX keeps the quick start at one backend
  process. An embedding service stays a later infrastructure option.

### Harness arms added

| arm | purpose |
|:--|:--|
| `blend_text_p[persona]` | step 1 as shipped |
| `nearest` | vectors alone (`$nearest`) |
| `hybrid_rrf` | Aito's `hybrid` rank fusion, for comparison; not shipped, because RRF can't compose with `$p` |
| `blend_three_way[persona]` | step 2 as shipped |
| **control:** `blend_three_way` with degenerate query vectors | must fall back to the text-only score |

The degenerate-vector control: a constant query vector and a random
unit vector. If the three-way arm still beats text-only with meaningless
vectors, the gain isn't coming from meaning, and the result doesn't
count.

## Acceptance criteria

- [ ] "food for an old dog", "kissanruoka" and "hundmat" return relevant
      results in both columns.
- [ ] Step 1: the right column's nDCG@10 is at least BM25's, within
      the bootstrap CI, for every persona. Zero-result rate 0 %.
- [ ] Step 2: the three-way arm beats step 1 on nDCG@10 with a CI
      that excludes zero. Finnish/Swedish is reported separately.
- [ ] The degenerate-vector controls score within the CI of text-only.
- [ ] The per-persona flip still shows: for "food", Maija's top 5 are
      cat products and Saara's are dog products.
- [ ] The backend refuses to start when the query model hash differs
      from `product_embeddings.meta.json`, with a message naming both.
- [ ] Right-column p50 latency is no worse than today's 2.4 s.

## Demo impact

`docs/demo-script.md` §Smart Search changes: the talking point moves
from "same results, reordered for the customer" to "one query:
the words, the meaning and this customer's purchase probability". The
side-by-side stays. The left column becomes a stronger baseline, which
makes the right column's gain more credible, not less. A good new
moment: a Finnish query where the left column finds little and the
right finds the products.

## Out of scope

- **Measuring personalisation.** The harness grades relevance from
  product attributes, so it can't see whether the ranking suits *this*
  customer. That needs labels from purchases. It waits on purchase data
  with real restocking and starter-kit patterns (a separate proposal).
- **Tuning θ beyond the defaults** unless the harness shows a gap
  worth it.
- **Embedding descriptions or attributes** (see above).
- **Approximate nearest-neighbour indexes.** `$nearest` is exact, and
  658 products don't need one.

## Consequences

**Good:**
- One query does all three jobs. The demo shows what a single store for
  text, vectors and prediction buys you, rather than describing it.
- Both columns stop returning nothing for natural queries.

**Bad:**
- Two new dependencies (`onnxruntime`, a tokenizer) and a model file.
  The multilingual model's large vocabulary makes it several hundred MB
  in full precision; an int8-quantised export is much smaller. The
  choice is measured on the harness (quantisation must not cost
  nDCG). The file isn't committed; `./do embed-products` fetches it
  and checks the hash.
- A schema change (`products.vec`) and a reload on the shared instance,
  which need the maintainer's yes.
