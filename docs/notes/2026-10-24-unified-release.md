# The unified release (started 2026-10-24)

Antti's brief: one coherent version on main that shows 360° intelligent
ecommerce, actionability and business impact, for partners (Ambientia,
Cartman, later Columbia Road).

## How it lands

- **Branch `unified`:** PR #64 (observable data, ADRs 0032/0033), PR #70
  (the discount what-if, estimate popovers in units) and main (ADRs
  0034–0041, the UCI page and backtest). Work PRs merge into it.
- **Main gets it in one cutover (ADR 0035):**
  1. the data promote onto master;
  2. the merge of `unified`;
  3. the deploy.
  
  Until then, main stays runnable on the old data.

## Workstreams

| # | Work | ADR | State |
|---|---|---|---|
| A | Site skeleton: sections, routes, redirects, Evidence index, Query patterns; the pure moves and drops | 0041 phase 1, 0037 | — |
| B1 | Product: history, price and discount what-ifs, links from the Shop | 0041, 0038 (view only) | — |
| B2 | Supply: demand, inventory, markdown, fair band | 0041 | — |
| B3 | Retention (churn, win-back) and Review triage | 0041 | — |
| B4 | Overview and Patterns (with Pattern Explorer and Basket Rules) | 0041 | — |
| B5 | Evidence pages: Search relevance, Model checks, Personalised search benchmark | 0037 | — |
| C | Data waits for its release: the app checks it on startup; precompute writes as master | 0035 | — |
| D | Demo script, README, partner copy; adversary verification | — | — |
| E | Data release 2: pre-registration, generator, offline checks (a new env; the load is Antti's) | 0038–0040 | — |

**Design rule for every owner view:** lead with the decision it supports
and its estimated impact (units, €, a share), with the reasons from
`$why`. Accuracy lives in Evidence, linked.
