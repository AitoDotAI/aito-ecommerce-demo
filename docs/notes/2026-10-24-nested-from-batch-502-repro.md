# Repro for aito-core: 502 on a stream of nested-`from` `_recommend` batches

Seen 2026-10-24 17:40–18:06 Helsinki on `shared.aito.ai` (2.11.8), env `release2`,
by `scripts/no_profile_shop_sweep.py`. Reads only. The same instance serves the
live demo, so nothing has been run since (`docs/verification/actionable-states-prereg.md`).

## The shape

Each sampled session is held out of the data by a nested `from`, so **every
session is a new population**. A session is 6 `_recommend` queries (3 variants,
each ranked once for the top 12 and once restricted to the products the session
showed). The body to `POST /_batch` is a JSON list of these:

```json
{"from": {"from": "impressions", "where": {"$not": {"context": "SESS-001932"}}},
 "where": {"context.month": "2026-03", "just_bought": false, "context.customer": "CUST-…",
           "context.pets_from_orders": {"$and": [{"$match": "cat"}]},
           "product_sku.pet_type": {"$or": ["cat"]}},
 "recommend": "product_sku", "goal": {"purchased": true}, "limit": 12}
```

`2026-10-24-nested-from-batch-502-repro.json` is the exact batch (3 sessions, 18
items) that was next when the run last stopped. Save it as `batch.json` and
send it to `POST /_batch` of the demo's database, env `release2`
(a copy of the demo's tables, loaded 2026-10-24; its counts are
in `data/release-env.json`).

## What happened

| run | batch size | until it stopped |
|:--|--:|:--|
| 1 | 15 sessions, 90 items | 8 batches, each 45–52 s of Aito time; then `502 Bad Gateway` (nginx/1.30.6) |
| 2 | 3 sessions, 18 items | 153 sessions in 7–8 minutes (batches 1–10 s of Aito time); then 502 |
| 3 | the same, resumed straight after | 153 more sessions (306 in all); then 502 |
| 4 | resumed | a 502 on the first batch of the run |

- The error body is nginx's HTML page, not Aito's JSON.
- `GET /version` answered 200 in 0.19 s right after each failure.
- The failing batch answers 200 when sent later, and its 18 queries answer 200
  one at a time (0.07–2.6 s each, the first of a session the slowest).
- The first query of each session is slow (1.5–2.6 s) and later ones fast, as
  for a cold slice.

## What we don't know

Whether the 502 is the upstream timing out, the engine restarting under the
load of many distinct populations, or memory. We guessed the last, with no
evidence. Please run `batch.json` in a loop with a different held-out session
each time against a local engine, and watch its memory and restarts.

## Update (2026-10-24, aito-core's answer, td-20261024151214916465)

Each held-out population is a full in-heap copy of `impressions`, cached by
the content of its kept rows. A "NOT this session" population is a new full
build per session and fills the heap. Core's safe options: (a) K folds, K
populations each built once; (b) one env branch with the held-out rows
deleted, then plain queries. We use (a) for the Shop sweep and the
personalised-search benchmark, and (b) for O4 (`_estimate`'s 501 on a nested
`from` is deliberate), after Antti's say-so for the branch writes. See the
two prereg amendments of 2026-10-24.
