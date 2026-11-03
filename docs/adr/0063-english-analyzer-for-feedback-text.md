# ADR 0063: Feedback text is indexed with Aito's English analyzer, and word patterns show the real phrase

**Status:** Proposed. Tried on a throwaway env (`analyzer-test`); nothing is changed in `master` and no schema file is edited yet.
**Date:** 2026-11-03
**Deciders:** Antti ("Aito uses Lucene analyzers"; "Let's cut the point of accuracy"). Engine review: the CPO session.

## Context

`reviews.text` and `nps_responses.comment` are declared with the `whitespace` analyzer (ADR 0012, ADR 0058), so a word is whatever sits between spaces.
The Analytics Feedback tab's word lists (ADR 0060 follow-up, PR #182) show the cost: "it.", "was" and "of" top the lists, and "damaged." and "damaged" count as two words.
An interim stop-word list in `scripts/feedback_patterns_prototype.py` hides the worst of it, but it patches a schema choice.

## Decision

1. Both columns use Aito's English language analyzer: `{"type": "language", "language": "english", "useDefaultStopWords": false, "customStopWords": [...]}`.
   Punctuation and case no longer split a word, and "arrived" and "arrive" are one word. The stop list is ours (articles, pronouns, auxiliaries, prepositions) and keeps negations:
   the default list removes "not", and "not disappointed" must stay different from "disappointed".
2. The review-triage `_predict` (category, sentiment, assigned to) reads the same column, so its numbers change. Measured on the `analyzer-test` env, train before 2025-11, test the 2,747 reviews from 2025-11:

   | Analyzer | category, assigned to | sentiment |
   |---|---|---|
   | whitespace (today) | 99.56 % | 99.93 % |
   | English, Aito's default stop words | 98.54 % | 99.89 % |
   | English, our stop list (keeps "not") | 98.62 % | 99.93 % |
   | commonest value | 59.70 % | 71.53 % |

   We accept the point of category accuracy. The generated texts are templated, so the whitespace score is probably partly the model reading the template and not the meaning;
   the word lists need real words. Calibration was not measured.
3. The rows behind a word pattern come from Aito (`_search` with `$match` on the pattern's stems), not from a Python re-implementation of the analyzer, which cannot reproduce stemming.
4. A word pattern is labelled with the real words, in the order they usually appear, with "…" where they are not next to each other ("arrived damaged", "packaging … crushed"),
   plus an example sentence with the words marked. Aito reports stems ("damag", "arriv"); `highlight` exists only in `_predict`, so a pure-Python stemmer (`snowballstemmer`, pinned)
   maps the words of the matching texts to their stems. Every stem it produces must be one Aito reports for that column, or the build fails; a test on fixed words ("arrived", "damaged", "packaging", "quality", "disappointed")
   shows drift in CI. This adds a dependency and needs Antti's yes; without it, the fallback is one `_search` `$match` per distinct word of the matching texts.
5. The interim stop-word list leaves the prototype script in the same change.

## Aito usage

Schema: the analyzer above on the two columns (a table rebuild and data reload, so an ADR 0035 data release). Queries: `_relate` and `$patterns` on the Text field return stems, as before;
`_search` with `{"text": {"$match": "damag arriv"}}` finds the rows. To check before the release: every filter the demo runs on these two columns, with `$has` and `$match`, gives the same answers before and after.
New query patterns go into `docs/aito-cheatsheet.md` in the same change.

## Acceptance criteria

- [ ] In the Feedback tab's Words view no row is a stop word, a punctuation variant of another row, or a stem shown raw.
- [ ] A pattern's "In group" count equals the number of rows listed behind it, for every stored pattern.
- [ ] "not disappointed" and "disappointed" are different words in the lists.
- [ ] The review-triage numbers on the Reviews page are re-measured and the page shows the new ones.
- [ ] The stem check fails on a stem Aito does not report.

## Demo impact

The Feedback tab's Words view reads as phrases. The Reviews page's triage accuracy drops by about a point. `docs/demo-script.md` quotes no accuracy for it.

## Out of scope

Other Text columns (they keep their analyzers). Highlighting in `_search` (an engine idea, not needed here). Languages other than English.

## Consequences

One data release for a schema change. A pinned dependency, if Antti agrees. About a point less category accuracy on the generated reviews.
