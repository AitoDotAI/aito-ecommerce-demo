# ADR 0063: Feedback text is indexed with Aito's English analyzer

**Status:** Accepted as the choice of analyzer; not yet applied. Tried on a throwaway env (`analyzer-test`); `src/schema.py` still declares `whitespace` and `master` is unchanged until a data release.
**Date:** 2026-11-03
**Deciders:** Antti ("Aito uses Lucene analyzers"; "Let's cut the point of accuracy"; "English analyzer is fine"). Engine review: the CPO session and core-4.

## Context

`reviews.text` and `nps_responses.comment` are declared with the `whitespace` analyzer (ADR 0012, ADR 0058), so a word is whatever sits between spaces.
The Analytics Feedback tab's word lists (ADR 0060 follow-up, PR #182) show the cost: "it.", "was" and "of" top the lists, and "damaged." and "damaged" count as two words.
An interim stop-word list in `scripts/feedback_patterns_prototype.py` hides the worst of it, but it patches a schema choice.

## Decision

1. Both columns use Aito's English language analyzer with our own stop list: `{"type": "language", "language": "english", "useDefaultStopWords": false, "customStopWords": [...]}`.
   Punctuation and case no longer split a word, and "arrived" and "arrive" are one word. The list is ours (articles, pronouns, auxiliaries, prepositions) and keeps negations:
   the default list removes "not", and "not disappointed" must stay different from "disappointed". Antti chose this analyzer ("English analyzer is fine").
2. The review-triage `_predict` (category, sentiment, assigned to) reads the same column, so its numbers change. Measured on the `analyzer-test` env, train before 2025-11, test the 2,747 reviews from 2025-11:

   | Analyzer | category, assigned to | sentiment |
   |---|---|---|
   | whitespace (today) | 99.56 % | 99.93 % |
   | English, Aito's default stop words | 98.54 % | 99.89 % |
   | English, our stop list (keeps "not") | 98.62 % | 99.93 % |
   | commonest value | 59.70 % | 71.53 % |

   The core-4 session measured the same direction (99.96 % to 99.49 % under every non-whitespace analyzer). We accept the point of category accuracy. The generated texts are templated
   (26 distinct sentences among the poor reviews), so the whitespace score is probably partly the model reading the template. Calibration was not measured.
3. **Not chosen:** a phrase (token n-gram) analyzer with the column's vocabulary as key words, which core-4 showed gives readable phrases ("arrived late", "not touch") and whole words.
   It costs the same triage point, and its vocabulary list must be regenerated in every data release or a new word is stemmed and splits from its peers. Also not chosen: an x-knowledge column
   (its triage is far worse on this text, and `_relate` returns the same single words).
4. **No stemmer dependency, no phrase labels.** The Feedback tab no longer lists words: ADR-less PR #188 replaced them with theme tags (`reviews.themes`, `nps_responses.themes`, `src/feedback_themes.py`), which read
   as phrases without any stem-to-word mapping. The stop-word list that was in `scripts/feedback_patterns_prototype.py` is gone with the word lists.
5. What the analyzer still changes: free-text `_relate`, `_predict` and `$match` on the two columns (the triage numbers above). It no longer feeds a view of its own, so it ships with a data release
   only if Antti wants the text indexed this way; the themes column does not depend on it.

## Aito usage

Schema: the analyzer above on `reviews.text` and `nps_responses.comment` (a table rebuild and data reload, so an ADR 0035 data release). Queries: `_relate`, `$patterns` and `$match` on the two columns now see
stems ("damag", "arriv"). Before the release, every filter the demo runs on these columns, with `$has` and `$match`, must give the same answers before and after, and the review-triage numbers are re-measured.
New query patterns go into `docs/aito-cheatsheet.md` in the same change.

## Acceptance criteria

- [ ] The Reviews page shows the re-measured review-triage accuracy, not the whitespace numbers.
- [ ] Every demo filter on the two columns gives the same rows before and after (`$has` / `$match`).
- [ ] "not" is indexed: "not disappointed" and "disappointed" are different queries with different counts.
- [ ] `src/schema.py` declares the analyzer and the stop list in one place a reader can find.

## Demo impact

The Reviews page's triage accuracy drops by about a point. `docs/demo-script.md` quotes no accuracy for it. The Feedback tab is unaffected: it groups by theme tags (PR #188).

## Out of scope

Other Text columns (they keep their analyzers). Phrase analyzers, knowledge columns, stem-to-word labels (see Decision 3 and 4). Languages other than English.

## Consequences

One data release for a schema change, for about a point less category accuracy and text indexed without punctuation noise. No new dependency.
