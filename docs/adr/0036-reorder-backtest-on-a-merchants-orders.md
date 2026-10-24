# ADR 0036: Backtest the reorder suggestion on a merchant's own orders

**Status:** Accepted (2026-10-23; R&D on, the CPO's order). The design and
decision rules below are fixed before any run on any dataset.

## Context

ADR 0034 shows Aito's draft of a business buyer's next order on UCI Online
Retail II, with a cleared claim from Aito core's benchmark. A merchant
evaluating Aito will ask the next question: does it work on *my* orders?
This ADR makes the benchmark a tool. It takes a merchant's order export,
replays history up to a date, asks Aito and three classical baselines for each
buyer's next order, and scores them against what the buyer actually ordered.

No number on any partner's data is promised. A merchant's result is theirs,
reported with its own uncertainty, and never quoted as ours.

## Decision

### Input adapters

All adapters produce the same three tables ADR 0034 loads: `customers`
(id only), `invoices` (invoice, customer_id link, `month` as `YYYY-MM`) and
`lines` (line_id, invoice link, `code` as a plain String, never linked).
The benchmark's `_predict` evidence is then the same whatever the source.

- **UCI Online Retail II:** ADR 0034's preparation, unchanged.
- **Shopify orders export** (Admin → Orders → Export, CSV):
  - one row per line item;
  - order = `Name`;
  - customer = `Email`, hashed with a salt before anything is stored, so no
    address reaches Aito or the report;
  - date = `Created at`;
  - code = `Lineitem sku`, or `Lineitem name` when the SKU is empty, counted
    and reported;
  - quantity = `Lineitem quantity`.
- **Fail loudly.** The adapter refuses a file whose header lacks any of these
  columns, and stops on an order whose lines disagree on customer or date.
- **Dropped rows are counted and reported,** never dropped silently:
  - cancelled orders (`Cancelled at` set);
  - fully refunded lines (`Financial Status` = `refunded`);
  - zero quantities;
  - orders without a customer (guest checkout).
- As in the benchmark, a basket is the set of its codes.

### The split (fixed per dataset before its run)

- **UCI:** train before 2011-09-01, test on and after, as benchmarked.
- **Any other dataset:** the cutoff date X is the first day of the month
  that holds the order at the 75th percentile of order dates. It's computed
  from the dates alone, written to the report's header, and committed before
  any metric is computed.
- Train = orders before X; only they are loaded into Aito. Test = each buyer's
  **first** order on or after X, as the benchmark's `targets()`.
- **Scored buyers:** those with a test order.

### The methods

| Method | Definition |
|---|---|
| Aito | `_predict` `{"from": "lines", "where": {"invoice.customer_id": id}, "predict": "code", "limit": 10}`, ADR 0034's query |
| Popularity | the most-bought codes in training |
| Personal repeat | the buyer's own codes by recency-weighted count, half-life as in the benchmark |
| EASE | λ = 250, as in the benchmark |

The baselines are copied from Aito core's benchmark
(`benchmarks/ecommerce-reco/baselines.py`, aito-core 625867faca), not
re-implemented.

### Metrics, slices and intervals

- **Primary:** hit@1, i.e. the top code is in the buyer's test order.
- **Secondary:** recall@10. Its ceiling (the best a 10-slot list can reach
  given basket sizes) is reported next to it.
- **Slices, always all three:** prior training orders 0, 1–2 and 3+. The
  slice counts are reported even when small.
- **Intervals:** each method's hit@1 and Aito − best baseline per slice, as
  paired 95 % intervals over buyers (normal approximation, ±1.96·SE). A
  slice under 30 buyers is reported with its interval and marked "too few to
  read".
- **"Best baseline" is per slice:** the strongest of the three in that slice
  on that dataset, decided by its point estimate. The report states which one
  it is.

### The report

- A Markdown report per run: dataset, cutoff, counts, dropped-row counts,
  the per-slice table with intervals, and 10 example buyers with Aito's top
  suggestion, its `$why`, and what they ordered.
- **Wording rules,** enforced in the report generator:
  - a slice whose interval for Aito − best baseline spans 0 is reported as
    "a tie";
  - "0 prior orders" is reported as a fallback ("Aito equals popularity
    here") when the point estimates are equal;
  - no sentence claims a win outside the slices whose interval excludes 0.

## Aito usage

The ADR 0034 env pattern, one env per dataset (`uci`, `backtest-<name>`):
the train tables are loaded, and only `_predict` is read. No new query shape.

## Acceptance criteria

- On UCI, the tool reproduces Aito core's table: Aito 197 of 636 in the 1–2
  slice (0.3097), EASE 0.1541 there, and a tie for 3+.
- Given a Shopify orders export with the documented columns, the adapter
  produces the three tables and reports its dropped rows. Given a file
  missing a column, it refuses and names the column.
- The report shows all three slices with intervals, names the best baseline
  per slice, and uses "a tie" where the interval spans 0.

## Out of scope

- A web page for the backtest. A script plus the report first; a page if
  partners want one.
- Product attributes as evidence (they would change the measured query).
- Any number on a partner's data in demo copy or sales material.
