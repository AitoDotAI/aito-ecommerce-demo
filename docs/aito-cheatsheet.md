# Aito query cheatsheet — `aito-ecommerce-demo`

Verified Aito query patterns used in this demo. **No new pattern lands
in `src/` without first appearing here.** That rule keeps Claude (and
any other contributor) from inventing query shapes — every entry below
has been run against the live PetNord data and the response shape
confirmed.

When a pattern is also documented in the cross-demo cheatsheets in
`aito-accounting-demo` and `aito-erp-demo`, link rather than duplicate.

---

## Index

_(empty — populated as views land)_

| View | Endpoint | Notes |
|---|---|---|

---

## Conventions

- Endpoints are written **without** the `/api/v1` prefix —
  `_predict`, `_relate`, `_recommend`, `_search`, `_evaluate`.
- Every example body is the literal payload sent over the wire,
  pretty-printed.
- The "Response shape" section pastes a real, slightly-trimmed
  Aito response so the reader sees the keys they'll need.
- "Gotchas" calls out anything Aito does that isn't obvious from the
  docs — index types, null handling, link semantics, default
  `select`. These have cost real time; record them so the next
  developer doesn't pay for the same lesson.

---

## Reference

- API docs: <https://aito.ai/docs/api/>
- Query language: <https://aito.ai/docs/api/query-language>
- Sister cheatsheets:
  - `aito-accounting-demo/docs/aito-cheatsheet.md`
  - `aito-erp-demo/docs/aito-cheatsheet.md`
