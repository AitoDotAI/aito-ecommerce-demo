# Aito performance findings (May 2026)

Slow paths and API gaps surfaced while making this demo fast enough
for live walkthroughs. Captured here so future iterations of this
repo don't regress, the core team can decide what to upstream, and
sibling demos (`aito-erp-demo`, `aito-accounting-demo`) can apply
the same fixes.

**Flag summary (full detail below).** Sorted by impact:

| # | Issue | Repro impact | Workaround |
|---|---|---|---|
| 1 | `httpx.request(...)` per call repeats TLS handshake every request | ~110 ms steady-state vs ~280 ms per call | Pooled `httpx.Client` |
| 2 | First call against a slice (`food` × `pet_size=small`) costs ~5 s | Olli persona pays 5 s on first food query after idle | Startup warmup pre-touches the slice |
| 3 | `basedOn` is not accepted on `EvaluateRecommend` / `EvaluateGroupedQuery` | Can't A/B-test the parameter via `_evaluate`; have to roll a Python hit-rate test | See `docs/aito-cheatsheet.md` §"Does `basedOn: []` cost accuracy?" |
| 4 | `basedOn` field names are *relative to the recommend target*, not the from-table | `["product_sku.category"]` → 400 `field 'product_sku.product_sku.category' not found` | Use `["category"]` when recommending `product_sku` |
| 5 | `basedOn` priors are redundant on broad personas (thick slices), decisive on cold SKUs / thin slices | Top-50 byte-identical across `basedOn` variants for Maija/Saara; only Olli (dog_owner ∩ small) shows reordering | Curate to features carrying segment signal — saves 13 % server time AND preserves the priors for thin-slice personas |

---

## 1. `httpx.request(...)` per call repeats TLS handshake every request

### Symptom

Every `_recommend` / `_search` / `_predict` call paid 200-300 ms of
"network overhead" on top of Aito's server-side time. Same code path
on a shared instance, same payloads, same client process — the
overhead repeated per call.

### Diagnosis

Aito returns its server-side execution time in the
`x-aitoai-response-time` response header. Splitting client wall-clock
against that header isolated the network/proxy cost cleanly:

```
requests.post() — fresh connection each call:
  #1: client=1533ms  server=1300ms  net=232ms
  #2: client=219ms   server=37ms    net=182ms
  #3: client=196ms   server=36ms    net=160ms
  #4: client=350ms   server=38ms    net=312ms
  #5: client=249ms   server=37ms    net=213ms

requests.Session() — pooled keep-alive connection:
  #1: client=249ms   server=38ms    net=211ms   ← TLS handshake
  #2: client=99ms    server=42ms    net=57ms    ← pooled
  #3: client=92ms    server=35ms    net=57ms
  #4: client=92ms    server=36ms    net=57ms
  #5: client=92ms    server=35ms    net=57ms
```

Pooled connection ⇒ network overhead drops from ~200 ms to **~57 ms**
(pure RTT). The 150 ms difference is the TLS handshake, paid once on
the first call and then never again.

`src/aito_client.py` was using `httpx.request(...)` — a top-level
helper that creates a *new* `httpx.Client` per call. The new client
opens a fresh TCP+TLS connection. Every call paid the handshake.

### Workaround

Switch to a pooled client held on the `AitoClient` instance:

```python
class AitoClient:
    def __init__(self, config: Config) -> None:
        # ...
        self._client = httpx.Client(headers=self._headers, timeout=90.0)

    def _request(self, method, path, json=None):
        response = self._client.request(method, self._url(path), json=json)
```

End-to-end measurement after the fix:

```
Pooled AitoClient:
  #1: client=300ms   ← TLS handshake amortised over process lifetime
  #2: client=110ms
  #3: client=110ms
  #4: client=110ms
  #5: client=112ms
  #6: client=125ms
```

**~3× faster on every steady-state request** — for free, no API
change, no protocol change.

### What we'd hope from core / library guidance

This is a client-side foot-gun in the demo, not an Aito-server issue.
But: the official `aito-client-python` SDK, if/when it exists, should
default to a pooled client. And the docs' Python examples should not
show `httpx.request(...)` per call as a pattern.

Sibling demos to apply the same fix:
- `aito-accounting-demo/src/aito_client.py:174` — same `httpx.request(...)` pattern
- `aito-erp-demo/src/aito_client.py:95` — same `httpx.request(...)` pattern
- `aito-demo` (JS) is fine — `fetch()` in modern Node pools via the global `undici` agent

### What we'd hope at the protocol level

The user asked: "if latency is dominated by TLS, how should the API
be designed? sockets/websockets?" Short answer — no, not at the API
level. The fix is purely client-side connection reuse:

1. **TCP/TLS connection reuse (keep-alive + client-side pooling)** —
   single biggest win, free. Pay one ~200 ms handshake per process
   boot, then every subsequent request costs ~RTT. This is what
   `requests.Session`, `httpx.Client`, Go's `http.Client`, Node's
   `Agent` all do by default. Most production "API is slow" problems
   trace back to this not being done.
2. **HTTP/2 multiplexing** — many parallel requests share one
   TCP+TLS connection. Useful when the app fans out
   (smart-search's `_search` + `_recommend` in parallel, price-view's
   7 parallel `_estimate` calls). `httpx.Client(http2=True)` enables
   it; needs `httpx[http2]` extra (`h2` package). Skipped here to
   avoid adding a dep for a small extra win on top of pooling.
3. **WebSockets / SSE** — solves a different problem entirely
   (server-pushed events, genuinely persistent client state). For a
   stateless query API, adds complexity without buying anything
   you don't already get from pooled HTTP.

---

## 2. First call against a slice costs ~5 s on a shared instance

### Symptom

After 90-120 s of idle, the *first* `_recommend` call to a specific
slice (`food/olli` — broad `$match` on name + `customer_pet_size:
small`) consistently jumped to ~5 s server time. Other slices
(`toy/saara`, `collar/maija`, `treat/olli`) stayed warm and answered
in 35-130 ms server time.

### Diagnosis

The `x-aitoai-response-time` header confirms the cost is server-side,
not network. Repeating the same query immediately after a cold first
call drops the server time from 5052 ms → 118 ms — classic LRU
working-set eviction.

```
Back-to-back, no waiting:
  food/olli   #1: 5339ms server   #2: 402ms   #3: 377ms   ← 13× cold penalty
  toy/saara   #1:  447ms          #2: 512ms   #3: 402ms   ← already warm
  collar/maija#1:  293ms          #2: 240ms   #3: 254ms   ← already warm

After 120 s idle:
  food/olli       5246ms total   5052ms server   194ms net   ← re-evicted
  toy/saara        342ms total    132ms server   210ms net   ← still warm
  collar/maija     235ms total     38ms server   197ms net   ← still warm
  treat/olli       332ms total    128ms server   203ms net   ← still warm
```

`food/olli` is the canary slice — broadest text-match (most candidate
products) intersected with the narrowest `pet_size` filter (`small`).
Largest working set ⇒ first to evict under memory pressure on the
shared instance.

### Workaround

Pre-warm in `src/cache_warmup.py` for the slices users hit first in
the demo path. Currently we warm `food × {maija, olli, saara}`. As
long as the demo's typical first interactions stay in this list, no
user pays the cold cost. Widening to also warm `toy`/`treat`/`collar`
× the three personas would cover free-typing further.

### What we'd hope from core

A documented "memory budget per instance" + eviction policy would let
us size warmup against it deliberately rather than empirically.
Currently it's "warm and pray nothing evicts before the demo ends".

---

## 3. `basedOn` not accepted on `EvaluateRecommend` / `EvaluateGroupedQuery`

### Symptom

To validate that `basedOn: []` on `_recommend` doesn't degrade
ranking quality, the natural test is to wrap the recommend in
`_evaluate` and compare accuracy with/without `basedOn`. Aito rejects
it:

```
400: invalid EvaluateRecommend. unexpected field 'basedOn'.
     Expected one of from, where, recommend, goal, select, offset, limit
400: invalid EvaluateGroupedQuery. unexpected field 'basedOn'.
     Expected one of train, test, testSource, select, group, goal, evaluate
```

`EvaluatePredict` and `EvaluateMatch` both accept `basedOn`;
`EvaluateRecommend` does not (verified against `coreapi.yaml`).

### Workaround

Two paths used in this repo:

- **`_evaluate predict product_sku`** with the same `where` columns —
  same conditional inference machinery, just inverted. `basedOn` is
  accepted here. Pixel-identical accuracy between `no-basedOn` and
  `basedOn: []` (0.7920 acc, 0.25 meanRank, 623.79 rankGain, n=500).
- **Client-side hit-rate test on `_recommend`** — sample held-out
  lines, run both variants, count truth in top-K. Hit@1 differed by
  1/150 rows (84.0 % vs 83.3 %); hit@5 and hit@10 perfectly equal.

Both paths in detail: `docs/aito-cheatsheet.md` §"Does `basedOn: []`
cost accuracy? Two evaluation shapes".

### What we'd hope from core

Either add `basedOn` to `EvaluateRecommend` schema, or document why
it's intentionally not there (perhaps because `_recommend` accuracy
isn't well-defined without a `group` discriminator).

---

## 4. `basedOn` field names are relative to the recommend target

### Symptom

Passing `basedOn: ["product_sku.category"]` to a `_recommend
product_sku` call returns 400:

```
field 'product_sku.product_sku.category' not found
```

Aito prefixed the recommend column name (`product_sku.`) onto the
already-qualified path, expanding to the nonexistent
`product_sku.product_sku.category`.

### Workaround

Use bare column names — relative to the recommend target. For
`recommend: "product_sku"`, write `["category", "brand"]`. Aito
resolves them against the `products` table via the link.

### What we'd hope from core

The error message could say: "Did you mean 'category'? `basedOn`
field paths are relative to the recommend target (`product_sku`)."

---

## 5. `basedOn` priors are redundant on broad personas, decisive on thin slices

### Symptom

After engineering segment ↔ {brand, dietary} affinity into the fixture
(per `BRAND_AFFINITY_BY_SEGMENT` / `DIETARY_AFFINITY_BY_SEGMENT`), I
expected `basedOn: ["pet_type", "brand", "dietary", "category"]` to
visibly reorder smart-search results for the demo's three personas.
Top-50 came back **byte-identical** to no-basedOn / `basedOn: []`
across every variant tested. Initial conclusion (wrong): "basedOn is
being ignored on `_recommend`".

### Diagnosis (from the Aito core team)

The parameter works fine. The byte-identity is a property of **slice
density**, not of Aito skipping the parameter:

- Direct `P(customer_segment | product_sku=X)` is dense on this
  dataset (600 SKUs × ~37 k order lines, broad sales).
- Coarser-grained priors from category / brand / pet_type are
  rolled-up summaries of the same purchasing signal already carried
  by the candidate identity itself. Informationally redundant on
  thick personas.
- The `$why` for olli/food (`tax_class:food-reduced 0.585,
  name:food 0.599, pet_type:dog 0.695`) shows the lifts sub-1 only
  because olli's slice is thin (dog_owner ∩ pet_size=small) and
  those features correlate negatively with the goal there. On
  Maija's or Saara's thicker slices the same features have lift
  ≈ 1 and the prior contribution normalises out.

Priors actually contribute when the direct lookup is sparse or
noisy. That's two situations the dataset's current shape mostly
avoids:

- **Cold candidates** — a brand-new SKU with no order_lines rows.
  Direct `P(seg | sku)` collapses to baseP; the prior is the only
  ranking signal.
- **Rare context slices** — segments of the conditioning space with
  few examples. Olli (dog_owner + pet_size=small) is the example
  in our dataset.

### Workaround

Curating `basedOn` to the four categorical features that correlate
with the segment goal is still the right move, for a different
reason than the affinity engineering was originally framed: it
cuts the prior computation from "all product features including
text-token and numeric columns" down to four. Measured
158 → 138 ms median server-time (-13 %) on smart-search's
`_recommend` call. The priors are running either way — `basedOn`
just restricts which features the prior computation visits.

### What we'd hope from core

Nothing on the engine — `basedOn` does what the docs say. A
sentence in the user-facing docs would help generalise the lesson:
**"`basedOn` matters when your direct candidate-identity signal is
sparse — cold SKUs, thin context slices, long-tail catalogs. On a
curated catalog with broad sales coverage, priors are mostly
redundant for thick personas but still contribute for thin
slices."** That's the lens we needed.

### How to validate when fixtures or personas change

The 4-of-5 empirical equivalence between `basedOn` variants on this
dataset depends on slice depth. Refresh the fixture or add a thin-
slice persona ⇒ equivalence may break for that persona. Recipe:
fetch top-50 with and without `basedOn` for each `(persona, query)`;
if they diverge, that persona lives on a thin slice and the priors
are moving the ranking — keep `basedOn` curated.

---

## How to reproduce these findings

Each can be re-measured cheaply against the live
`shared.aito.ai/db/aito-ecommerce-demo`:

```bash
# Finding 1 — pooled vs unpooled
uv run python -c "
import requests, time
from src.config import load_config
cfg = load_config()
url = f'{cfg.aito_api_url}/api/v1/_recommend'
hdrs = {'x-api-key': cfg.aito_api_key, 'Content-Type': 'application/json'}
body = {'from': 'order_lines', 'where': {'product_sku.name': {'\$match': 'collar'}}, 'recommend': 'product_sku', 'goal': {'customer_segment': 'cat_owner'}, 'basedOn': [], 'limit': 10}
sess = requests.Session()
for fn, label in [(requests.post, 'fresh'), (sess.post, 'pooled')]:
    print(label)
    for i in range(5):
        t0 = time.perf_counter()
        r = fn(url, headers=hdrs, json=body, timeout=30)
        c = (time.perf_counter()-t0)*1000
        s = float(r.headers['x-aitoai-response-time'])
        print(f'  #{i+1} client={c:.0f}ms server={s:.0f}ms net={c-s:.0f}ms')
"

# Finding 2 — eviction window
# See docs/aito-cheatsheet.md and the conversation that produced
# this notes file for the eviction-test script.
```
