# Planted incidents: the data against its nulls (ADR 0056)

Seeds 42, 7 and 99, pooled. Each null switches one incident off. Margins are the ADR's.

| Check | What | Value | Margin met |
|---|---|---|---|
| E1-bad | bad-unit share of the line in the incident months, planted ÷ null | 6.929 | yes |
| E1-reviews | share of 1–2 star reviews of the line in the incident months, planted − null (points) | 69.231 | yes |
| E1-hit | units of the line in the batch months, planted ÷ null (a house-label hit) | 2.192 | yes |
| E1-pulled | units of the line after the pull, planted | 0.000 | yes |
| E1-null-sells | units of the line after the pull, null (it would have sold) | 427.000 | yes |
| E1-trust | other grain-free dog dry food in the two months after the pull, planted ÷ null | 1.116 | **no** |
| E1-churn | churn of the batch's buyers, planted ÷ null | 1.007 | **no** |
| E2-bad | bad-unit share of the line in the incident months, planted ÷ null | 4.500 | yes |
| E2-reviews | share of 1–2 star reviews of the line in the incident months, planted − null (points) | 33.333 | yes |
| E2-switch | the bad-unit customers' repeat units of the line, planted ÷ null (same customers' number of units per customer) | 0.308 | yes |
| E2-others | the other buyers' repeat units per customer, planted ÷ null | 0.960 | yes |
| E3-bad | bad-unit share of the line in the incident months, planted ÷ null | 3.750 | yes |
| E3-reviews | share of 1–2 star reviews of the line in the incident months, planted − null (points) | 37.143 | yes |
| E3-switch | the bad-unit customers' repeat units of the line, planted ÷ null (same customers' number of units per customer) | 0.000 | yes |
| E3-others | the other buyers' repeat units per customer, planted ÷ null | 0.222 | **no** |
| E4-bad | bad-unit share of the line in the incident months, planted ÷ null | 16.000 | yes |
| E4-reviews | share of 1–2 star reviews of the line in the incident months, planted − null (points) | 77.778 | yes |
| E4-switch | the bad-unit customers' repeat units of the line, planted ÷ null (same customers' number of units per customer) | 0.188 | yes |
| E4-others | the other buyers' repeat units per customer, planted ÷ null | 1.042 | yes |

## Reading (2026-11-01, first run, margins as pre-registered in ADR 0056)

16 of 19 checks pass. The three that do not, and why, found by reading the generator and the numbers:

- **E1-trust (1.116, needs at most 0.95).** After the pull, households whose grain-free salmon staple is gone pick another grain-free food, which
  adds more units to the rest of the type than the ×0.90 trust dip takes away. The dip is real in the odds (`tests/test_planted_incidents.py`)
  and invisible in the units of the other grain-free dog foods. Not yet changed: to show it, the dip has to outweigh substitution (a factor near 0.7),
  or the check has to read the whole type including the pulled line, where the pull itself is the drop.
- **E1-churn (1.007, needs at least 1.3).** A bad unit raises the churn hazard through the existing chain (R4), which is small, and most of the
  batch's buyers did not get a bad unit (about 44 %), so their churn is the null's. Not yet changed: the recall needs its own, larger hazard for the
  customers whose dog got ill, as the ADR intended ("churn more").
- **E3-others (0.222, needs within 0.10 of 1).** A line that sells little: pooled over three seeds only a handful of other buyers, who bought the
  line 1 to 5 times in all. Too few to say that the other buyers moved; neither check can tell a drop from noise at this size. A two-month window
  would double the sample.

These are changes to the planted effects after seeing the data, so they are Antti's to accept before the generator is changed; the switches stay off in
the committed fixtures, which are byte-identical to before.
