# ADR 0058: Feedback with text and context: NPS comments, reviews that read like their stars, and metadata inferred from them

**Status:** Accepted, `T1` and `T2` built behind switches (off in the committed fixtures); the inference is not built. Proposed 2026-11-01, Antti: "NPS responses could contain the textual feedback", "they could mention also products beside other topics", "we could infer metadata based on the feedback context"; "0058")
**Verified on generated data:** docs/verification/feedback-text-data.md.
**Date:** 2026-11-01
**Deciders:** Antti

## Context

An NPS answer today is a score, its group, the month and whether the customer also wrote a negative review. There is no text, so nothing says *why* a
customer is a detractor. The reviews have text, but it is drawn from a template per topic and does not look at the stars or the product: "Five stars — the box arrived
crushed" sits next to a 5-star review, and the raw-data widget on the Customers view shows it. The recall and quiet incidents of ADR 0056 would be invisible in the
text even though they are in the stars and the returns.

## Decision

Three changes, each behind a switch that is off in the committed fixtures until the data release that carries them (as with ADR 0056), so with them off the fixtures
are byte-identical to today's, which a test shows.

1. **NPS comments (`T1`).** `nps_responses` gains a nullable `comment`. About a quarter of the passives and half of the promoters and detractors leave one. The comment
   is built from clauses the generator already knows the cause of: the product on the order (named), the delivery (a late or damaged one, a return), the experience
   (bad, ok, good), and the overall feeling for the group. A comment can mention a product *and* a second topic ("The salmon kibble was fine, but delivery took ten days").
   The ground truth (the topics and the product each comment mentions) goes to the answer key, never to the table.
2. **Reviews that read like their stars (`T2`).** A review's text is drawn from clauses for its stars and topic and names the product, from its own random stream, so no other
   draw moves. 1–2 stars read as complaints, 5 stars as praise.
3. **Incidents in the text.** With ADR 0056's incidents on, a bad unit from the recalled batch says the dog got ill (symptoms, never deaths), and a bad unit from a quiet
   incident says what was wrong (taste, smell, texture). Customers who switch for good say so.

### Metadata inferred from the text (after the data is loaded)

A comment is free text, and the shop wants it as data: which topics it raises, which product it names, whether it is a complaint. Aito predicts these from the text,
as Review triage predicts a review's topic: `_predict` on the comment's text field, with the topic or product as the target, over the comments that are labelled.
The check is the answer key: how often the predicted topic and the named product are the true ones, against a baseline that predicts the most common topic. The result is
reported as measured. This part needs the table in Aito (a release load, which Antti runs) and is not built here.

## Aito usage

Unchanged until the inference: `nps_responses` gains one text column; the predictions use `_predict` with a text input as in Review triage (`docs/aito-cheatsheet.md`).

## Acceptance criteria

- [ ] With `T1` and `T2` off, `./do generate-fixtures` writes the committed fixtures byte for byte.
- [ ] With `T1` on, a share of the NPS answers carries a comment that names the order's product, mentions at least one cause the generator knows, and that a test can trace to the answer key.
- [ ] With `T2` on, no review of 1–2 stars reads as praise and none of 5 stars as a complaint (checked on the generated fixtures); every review names its product.
- [ ] With the incidents on as well, a bad unit from the recalled batch is described as making the animal ill, and none says anything about deaths.
- [ ] No real name, brand or event appears in the texts.
- [ ] The Customers view's NPS answers tab shows the comment.

## Demo impact

`docs/demo-script.md`: the Customers view's NPS answers tab reads like a shop's feedback; with the incidents on, the recall is visible in the words.

## Out of scope

Loading the table into shared Aito and the inference itself (the data release; Antti's decision, after the quoted figures are re-checked); languages other than English; replies to comments;
anything the shop would do with a comment automatically.
