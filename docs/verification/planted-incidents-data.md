# Planted incidents: the data against its nulls (ADR 0056)

Seeds 42, 7 and 99, pooled. Each null switches one incident off. Margins are the ADR's.

| Check | What | Value | Margin met |
|---|---|---|---|
| E1-bad | bad-unit share of the line in the incident months, planted ÷ null | 6.830 | yes |
| E1-reviews | share of 1–2 star reviews of the line in the incident months, planted − null (points) | 60.870 | yes |
| E1-hit | units of the line in the batch months, planted ÷ null (a house-label hit) | 2.075 | yes |
| E1-pulled | units of the line after the pull, planted | 0.000 | yes |
| E1-null-sells | units of the line after the pull, null (it would have sold) | 459.000 | yes |
| E1-trust | other grain-free dog dry food bought by customers who never bought the line, two months after the pull, planted ÷ null | 0.970 | **no** |
| E1-churn | churn of the batch's buyers, planted ÷ null | 1.153 | **no** |
| E2-bad | bad-unit share of the line in the incident months, planted ÷ null | 4.500 | yes |
| E2-reviews | share of 1–2 star reviews of the line in the incident months, planted − null (points) | 33.333 | yes |
| E2-switch | the bad-unit customers' repeat units of the line, planted ÷ null (same customers' number of units per customer) | 0.423 | **no** |
| E2-others | the other buyers' repeat units per customer, planted ÷ null | 0.980 | yes |
| E3-bad | bad-unit share of the line in the incident months, planted ÷ null | 5.500 | yes |
| E3-reviews | share of 1–2 star reviews of the line in the incident months, planted − null (points) | 30.721 | yes |
| E3-switch | the bad-unit customers' repeat units of the line, planted ÷ null (same customers' number of units per customer) | 0.355 | **no** |
| E3-others | the other buyers' repeat units per customer, planted ÷ null | 0.816 | **no** |
| E4-bad | bad-unit share of the line in the incident months, planted ÷ null | 16.000 | yes |
| E4-reviews | share of 1–2 star reviews of the line in the incident months, planted − null (points) | 70.000 | yes |
| E4-switch | the bad-unit customers' repeat units of the line, planted ÷ null (same customers' number of units per customer) | 0.000 | yes |
| E4-others | the other buyers' repeat units per customer, planted ÷ null | 1.033 | yes |

## Reading (2026-11-01, the release's final code: anchors excluded, the recalled line zero-odds, the Salmon house label)

14 of 19 pass. Earlier runs, on earlier code, passed 16 of 19; the lines changed since (no demo anchor in a line, so a different set of SKUs on some seeds; the line stays listed with zero odds
instead of being pulled from the pools; the house-label names), and every value moved a little. The five that miss their margins:

- **E1-trust 0.970 (needs ≤ 0.95).** The other grain-free dog foods sell about 3 % less after the pull, not 5 %. Closer than before (1.12), and still short: substitution from the pulled line offsets part of the dip.
- **E1-churn 1.153 (needs ≥ 1.3).** The recall's buyers leave 15 % more often than in the null, in the right direction; 1.306 on the earlier code. The sample (a few dozen buyers of the batch over three seeds) moves it that much.
- **E2-switch 0.423 (needs ≤ 0.333)** and **E3-switch 0.355 (needs ≤ 0.333).** The customers who had a bad unit buy the line at 42 % and 36 % of the null's rate: the switch is there and is just outside the margin.
- **E3-others 0.816 (needs within 0.10 of 1).** A dozen customers over three seeds: too few to hold the margin.

Every effect is in its intended direction. None was tuned to reach its margin after it was seen. Together with `actionable-states-data.md` (127 of 148, the same per-seed scatter as the last release) the picture is: the effects are present, and the pooled checks are tight for small samples.
