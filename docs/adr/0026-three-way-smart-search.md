# ADR 0026: Smart Search as one three-way blend — text × meaning × purchase probability

**Status:** Proposed. Step 1 built and measured (see §Step 1 results); awaiting maintainer review
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
| BM25 over the name (`$similarity`), not shipped | 0.599* | 0 % |

\* Inflated by table order; the honest figure is 0.518. See §Step 1 results.

`$match` requires every query word in the product name. Natural
phrasing ("food for an old dog"), misspellings and Finnish/Swedish
queries return nothing, in **both** columns: the predictive column can
only reorder what the filter lets through. BM25 fixes much of that
(+0.225 nDCG@10, 95 % CI [+0.141, +0.318], honest figures), but it is
still word matching. Finnish/Swedish queries match no English product
name at all (0.000).

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

## Step 1 results (2026-09-27)

Measured with `./do search-eval`; full tables in
`docs/verification/search-eval.md`.

**A correction to the baseline above.** BM25 ties every product at
lift 1.0 when no query word matches, and Aito returns ties in table
order. The products table starts with dog dry food, so unmatched dog
queries ("hundmat", "koiranruoka", "canine kibble") scored a perfect
1.0 by accident. Dropping rows with `$score == 1.0` gives honest BM25
0.518 (not 0.599), 30 % zero-result, and **0.000 on Finnish/Swedish**
(not 0.233). A table-order control arm (0.196, twice chance) now shows
the free credit that ordering gives.

**The text weight.** At Aito's default θ 0.33, purchase probability
drowned the words (nDCG@10 0.31; a cat owner's "food for an old dog"
returned cat food). The shipped value is **θ 3.0**: the smallest tried
that keeps pet-specific queries on that pet. At 2.0, a cat owner's
"dog food" still had cat food at ranks 7-10. Chosen on the same query
set; every value tried is reported.

| acceptance criterion | result |
|:--|:--|
| Both columns improve | left +0.225 [+0.141, +0.318]; right +0.273 to +0.294 per persona, all intervals above zero |
| Right column ≥ left (BM25) | better for every persona: +0.047 to +0.069, all intervals above zero |
| Right column zero-result rate 0 % | 0 % |
| Maija/Saara flip for "food" survives in the `get` form | yes: top 5 all cat / all dog (`test_smart_search_food_flips_between_cat_and_dog_owner`) |
| Latency no worse than 2.4 s p50 | p50 107-141 ms, p95 ≤ 331 ms |
| "food for an old dog" returns relevant results in both columns | yes |
| "kissanruoka" / "hundmat" return relevant results | **no, step 2**: no English name matches; the right column falls back to purchase probability (~0.2, near chance) |

**Found while building: an unlabelled fallback.** When no product name
contains any query word ("dogfood"), the right column ranks on
purchase probability alone. For a dog owner that's puppy treats, under
a heading saying "× text relevance". The response now carries
`text_matched`, and the page says "No product name matches … showing
what this customer is most likely to buy instead".
