# Planted incidents: the data against its nulls (ADR 0056)

Seeds 42, 7 and 99, pooled. Each null switches one incident off. Margins are the ADR's.

| Check | What | Value | Margin met |
|---|---|---|---|
| E1-bad | bad-unit share of the line in the incident months, planted ÷ null | 6.723 | yes |
| E1-reviews | share of 1–2 star reviews of the line in the incident months, planted − null (points) | 65.385 | yes |
| E1-hit | units of the line in the batch months, planted ÷ null (a house-label hit) | 2.113 | yes |
| E1-pulled | units of the line after the pull, planted | 0.000 | yes |
| E1-null-sells | units of the line after the pull, null (it would have sold) | 467.000 | yes |
| E1-trust | other grain-free dog dry food bought by customers who never bought the line, two months after the pull, planted ÷ null | 1.119 | **no** |
| E1-churn | churn of the batch's buyers, planted ÷ null | 1.306 | yes |
| E2-bad | bad-unit share of the line in the incident months, planted ÷ null | 4.500 | yes |
| E2-reviews | share of 1–2 star reviews of the line in the incident months, planted − null (points) | 33.333 | yes |
| E2-switch | the bad-unit customers' repeat units of the line, planted ÷ null (same customers' number of units per customer) | 0.296 | yes |
| E2-others | the other buyers' repeat units per customer, planted ÷ null | 1.020 | yes |
| E3-bad | bad-unit share of the line in the incident months, planted ÷ null | 5.524 | yes |
| E3-reviews | share of 1–2 star reviews of the line in the incident months, planted − null (points) | 34.194 | yes |
| E3-switch | the bad-unit customers' repeat units of the line, planted ÷ null (same customers' number of units per customer) | 0.354 | **no** |
| E3-others | the other buyers' repeat units per customer, planted ÷ null | 0.857 | **no** |
| E4-bad | bad-unit share of the line in the incident months, planted ÷ null | 6.000 | yes |
| E4-reviews | share of 1–2 star reviews of the line in the incident months, planted − null (points) | 72.727 | yes |
| E4-switch | the bad-unit customers' repeat units of the line, planted ÷ null (same customers' number of units per customer) | 0.308 | yes |
| E4-others | the other buyers' repeat units per customer, planted ÷ null | 0.960 | yes |

## Reading (2026-11-01, third run, after the changes of the ADR's second amendment)

16 of 19 checks pass; E1-churn now does (1.306 against 1.3). The three that do not:

- **E1-trust (1.119, needs at most 0.95).** Even among customers who never bought the line, the other grain-free dog foods sell *more* after the pull, not less.
  The trust dip multiplies the odds of a purchase, and for a restock of a staple the purchase probability is already near 1, so a factor of 0.7 on the odds moves
  it very little (the odds scale saturates). The dip is in `purchase_odds` and tested there, and does not reach the units. To make it visible it has to act on what
  the household chooses (a share of households leaves the type) and not on the odds of a purchase they intend. That is a change to how the generator draws a
  staple, so it is not made here.
- **E3-switch (0.354, needs at most 0.333)** and **E3-others (0.857, needs within 0.10 of 1).** The switch is there (a third of the null's repeat purchases of
  the line) and is just outside the margin; the other buyers are too few to hold a 10 % margin (a dozen customers over three seeds). The line is the house-label
  dog treats, as many SKUs as there are; it does not sell more.

Nothing here is tuned to pass. The committed fixtures are unchanged (switches off, byte-identical to before).
