# Semantic and hybrid product search: pre-registration (ADR 0026 step 2, td-20260928211130690878)

**Fixed:** 2026-10-30, before any vector arm was built or scored.
**Status:** proposed; nothing below runs until the gates at the end are cleared.
**Question:** does adding meaning (embeddings) to today's search find products that today's search does not, without losing what it finds?

A change after a result is seen is an amendment at the end of this file, dated, with its reason. A bar is never moved.

## What was seen before this was written

- ADR 0026 step 1 results, on the 60 queries in `data/search_eval/queries.json`: BM25 0.518 nDCG@10, shipped right column 0.57–0.59 per persona, Finnish/Swedish 0.000 on BM25. Those queries were also used to choose θ 4.0, so they are the tuning set.
- No vector arm has been built or scored, on any query set.
- The held-out queries below were written without running any search; the only check made on them is that the existing grader gives each at least three grade-2 products in the catalogue (all 60 do).

## The held-out query set

`data/search_eval/queries_heldout.json`, sha256 `e37912ae656429f59c4868dc64a5f668164e46b7c7255fb71eb17b20575bf695`.
60 queries, 10 in each of exact, brand, synonym, paraphrase, misspelling, nordic. Same spec format and grader as the tuning set (`src/search_eval/relevance.py`: grade 2 = pet, category and refinement all hold; grade 1 = pet/category only). No query text appears in `queries.json`. It is used once, for the result, and never to choose a parameter.

**Parameter choice** (the only tuning allowed): the three-way blend's vector weight θ_vec is chosen from {0.87, 2, 4, 8} on the 60 tuning queries only, by nDCG@10 over the semantic strata. θ_text stays at the shipped 4.0. The chosen θ_vec is written to the run's output before the held-out queries are scored.

## Arms

| arm | what it is | bar |
|:--|:--|:--|
| `shipped` | today's right column: `$p × $similarity`, θ 4.0, scored per persona (Maija, Olli, Saara) and averaged per query | the baseline |
| `bm25` | today's left column | reported |
| `nearest` | `$nearest` alone | reported |
| `hybrid_rrf` | Aito's rank fusion | reported |
| `three_way` | `$p × $similarity × $vectorIdf`, per persona, averaged per query | the candidate |
| control: constant vector | `three_way` with a constant query vector | P6 |
| control: random vector | `three_way` with a random unit query vector | P6 |
| control: table order, random order | as in the existing harness | P7 |

Vectors: `intfloat/multilingual-e5-small`, product `name` only (ADR 0026: embedding attributes would hand the arm the answer key). Rows whose `$score` is exactly 1.0 are dropped from the lexical arms, as in the step 1 correction (ties return in table order).

## Metric and test

nDCG@10 per query, each query's value the mean over the three personas. Differences are paired by query, 95 % interval from a seeded bootstrap (10,000 resamples, seed 0, the harness's own `paired_bootstrap_ci`). A difference whose interval spans 0 is called a tie.

## Bars (all must hold; fixed now)

| # | claim | bar |
|:--|:--|:--|
| P1 | meaning helps overall | `three_way` − `shipped`, all 60 queries: ≥ +0.05, interval lower bound > 0 |
| P2 | meaning helps where words fail | same difference on synonym + paraphrase + misspelling + nordic (40 queries): ≥ +0.10, interval lower bound > 0 |
| P3 | and costs nothing where words work | same difference on exact + brand (20 queries): ≥ −0.03 (point estimate; the interval is reported) |
| P4 | Finnish/Swedish is reachable | `three_way` nDCG@10 on the 10 nordic queries ≥ 0.30 (`shipped` is expected near 0) |
| P5 | no empty results | zero-result rate 0 % on all 60 |
| P6 | the gain is meaning, not noise | both vector controls within ±0.02 nDCG@10 of `shipped`, all 60 queries |
| P7 | the metric rewards relevance | `bm25` > table order and > random order, each with interval lower bound > 0 |
| P8 | personalisation survives | for "food", Maija's top 5 are all cat products and Saara's all dog (the existing live test) |
| P9 | still fast | `three_way` p95 ≤ 300 ms per query on the engine it ships on (step 1 measured p95 ≤ 244 ms) |

A vector arm beating lexical on exact or brand is reported as a harness smell, not as a win (ADR 0026's own rule).

## What each outcome means

- **All of P1–P9 hold:** the result is proposed to Antti with the numbers; shipping is his call.
- **P1 or P2 fails:** semantic search does not earn its place on this catalogue and this query set. Reported as such; the result file stays.
- **P3 or P6 fails:** it helps by hurting, or the gain is not meaning. Reported; not shipped.
- **Anything else fails:** reported with the failing bar named. No retuning to pass: a new design is a new prereg.

## Limits, said before the run

- Relevance comes from structured attributes, not from what shoppers bought, so this cannot say whether a ranking suits *this* customer (ADR 0026 §Out of scope).
- Ten queries a stratum: the per-stratum intervals will be wide. The bars are on pooled groups for that reason.
- One synthetic catalogue of 658 products, with English names only. Nordic queries are graded by pet and category, since no product name is Finnish or Swedish.

## Gates before anything runs (not decisions made here)

- An engine at v2.11.0 or later, where the Vector type and `$vectorIdf` are measured (ADR 0026).
- A `products.vec` column and an env load on the shared instance: a shared write, Antti's yes.
- The embedding model file pinned by SHA-256, with the backend refusing to start on a mismatch (ADR 0026).
- New dependencies (`onnxruntime`, a tokenizer): proposed to Antti first (CLAUDE.md).

## Amendments

### 2026-10-30, before any run: where it runs, and who graded

Made on the CPO's review. None of it touches a bar.

1. **The evaluation runs on a local Aito engine** (v2.11.9 JAR), loaded from the demo fixtures plus a \`products.vec\` column. No shared write. The shared env load waits until the result is a win.
2. **The embedding step lives in a separate experiment environment** under \`experiments/semantic-search/\`, with its own virtualenv and requirements. The demo's runtime dependencies do not change. The model file is pinned by SHA-256, recorded in the run's output. Adding \`onnxruntime\` to the demo itself is a question for Antti only if the result is a win and it ships.
3. **Who graded the 60 held-out queries.** Nobody and nothing judged search results. Each query is a spec (text, pet, categories, refinement) over the product's structured attributes, and \`src/search_eval/relevance.py\` grades every catalogue product against it with fixed rules. The 60 specs were written by Claude (model \`claude-sonnet-5-5\`) in the maintainer's session on 2026-10-30, from the catalogue's brands, categories, diet tags and name tokens. They were written before any search or embedding was run, and the author saw no candidate output of any arm. The only checks made after writing: no query text repeats one in \`queries.json\`, and each has at least three grade-2 products. The grader is code and sees only product attributes. The prompt is not recorded because no model graded: the specs are the file itself.

Not yet done, and why: downloading the embedding model, the engine JAR (if not already on the machine) and installing \`onnxruntime\` in the experiment environment. Those are downloads and an install the maintainer has not yet approved in this session.
