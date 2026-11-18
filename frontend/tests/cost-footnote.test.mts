// Run: node --test frontend/tests/   (./do frontend-test). The footnote's sentence is built in lib/cost-footnote.ts so its spacing is tested without a browser.
import assert from "node:assert/strict";
import test from "node:test";

import { costFootnote } from "../lib/cost-footnote.ts";

const FACTS = { kept_lines: 34955, lines_below_cost: 169, unit_cost_share_of_list_price: 0.68 };

test("the cost footnote puts a space between the line count and 'kept'", () => {
  assert.match(costFootnote(FACTS), /34,955 kept lines/);
});

test("the cost footnote states each stored fact once, in words a reader can parse", () => {
  assert.equal(
    costFootnote(FACTS),
    "(about 68 % of the list price) applied to two years of sales, and 169 of 34,955 kept lines were sold below it.",
  );
});
