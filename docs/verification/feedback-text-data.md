# Feedback text: the generated data against ADR 0058's criteria

Seed 42, generated once with `T1`, `T2` and the four incidents on (a temporary directory; nothing written to `data/`), checked by reading the written fixtures.

| Criterion | Result |
|---|---|
| With `T1` and `T2` off the fixtures are byte-identical | 18 of 18 files identical to the committed ones |
| A review of 1–2 stars does not read as praise (712 reviews) | 0 do |
| A review of 4–5 stars does not read as a complaint (3,661 reviews) | 0 do |
| Every review names its product | 5,207 of 5,207 |
| NPS answers with a comment | 1,245 of 3,209 (39 %): promoters 49 %, detractors 48 %, passives 23 % |
| Comments carry their ground truth in the answer key (`answer_key/nps_comments.json`) | 1,245 rows: product 989, overall 410, quality 197, delivery 175, returns 102, health 3 |
| A bad unit from the recalled batch is described as making the animal ill | 3 comments and 2 reviews say so; none mentions death |
| The recalled line carries the house label in every text | 0 texts use its old catalogue brand (found and fixed: they did before) |
| No real name, brand of the incident or event in any text | 0 |

The check reads the product's name out of a review before looking for praise or complaint words: "Fresh Breath Dental Treats" is a product, not a verdict.

Few recalled comments (3) because few answers follow a bad unit of the recalled line (about 90 purchases a month of that line, 35 % bad, half of those surveyed, half of those commenting).
