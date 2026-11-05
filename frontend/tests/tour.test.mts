// Run: node --test frontend/tests/   (./do frontend-test). The tour's rules live in lib/tour.ts without React, so they are tested without a browser.
import assert from "node:assert/strict";
import test from "node:test";

import { MENU_LINK, autoStart, choseAView, escapeClosesTour, markSeen, shouldAutoStart, stepsFor, viewForPath, type View } from "../lib/tour.ts";

const VIEWS: View[] = [
  { href: "/", label: "Overview" }, { href: "/retention", label: "Retention" }, { href: "/evidence", label: "Index" }, { href: "/evidence/model-checks", label: "Model checks" },
];
const memory = (initial: Record<string, string> = {}) => {
  const data = { ...initial };
  return { getItem: (key: string) => data[key] ?? null, setItem: (key: string, value: string) => { data[key] = value; }, data };
};
const broken = { getItem: () => { throw new Error("storage blocked"); }, setItem: () => { throw new Error("storage blocked"); } };

test("a first visit starts the tour", () => {
  assert.equal(shouldAutoStart(memory()), true);
});

test("a visitor who has seen the tour is not shown it again", () => {
  const storage = memory();
  markSeen(storage);
  assert.equal(shouldAutoStart(storage), false);
});

test("the tour does not start when storage throws, since it could not remember being dismissed", () => {
  assert.equal(shouldAutoStart(broken), false);
});

test("the tour does not start when there is no storage at all, and nothing is written", () => {
  assert.equal(shouldAutoStart(undefined), false);
  assert.equal(autoStart({ store: undefined, demoMode: false }), false);
});

test("marking the tour seen does not throw when storage does", () => {
  assert.doesNotThrow(() => markSeen(broken));
});

test("a path finds its view, ignoring the trailing slash of a static export, and the longest match wins", () => {
  assert.equal(viewForPath("/retention/", VIEWS)?.label, "Retention");
  assert.equal(viewForPath("/evidence/model-checks/", VIEWS)?.label, "Model checks");
  assert.equal(viewForPath("/", VIEWS)?.label, "Overview");
  assert.equal(viewForPath("/nowhere", VIEWS), undefined);
});

test("on the front page the tour starts with what this is, then the menu, then the Why", () => {
  const steps = stepsFor({ view: VIEWS[0], viewCount: 17 });
  assert.deepEqual(steps.map((s) => s.id), ["what", "menu", "why"]);
  assert.match(steps[1].text, /17 views/);
});

test("on a deep link the tour starts with the view the visitor is on, then the menu", () => {
  const steps = stepsFor({ view: VIEWS[1], viewCount: 17 });
  assert.deepEqual(steps.map((s) => s.id), ["here", "menu", "why"]);
  assert.match(steps[0].title, /You are on Retention/);
});

test("a path that is no view gets the front-page tour", () => {
  assert.deepEqual(stepsFor({ view: undefined, viewCount: 17 }).map((s) => s.id), ["what", "menu", "why"]);
});

test("the menu step says tap on a phone and click on a desktop", () => {
  assert.match(stepsFor({ view: VIEWS[0], viewCount: 17, touch: true })[1].text, /Tap/);
  assert.match(stepsFor({ view: VIEWS[0], viewCount: 17, touch: false })[1].text, /Click/);
});

test("starting by itself marks the tour seen, so a reload does not start it again", () => {
  const storage = memory();
  assert.equal(autoStart({ store: storage, demoMode: false }), true);
  assert.equal(shouldAutoStart(storage), false);
  assert.equal(autoStart({ store: storage, demoMode: false }), false);
});

test("a demo being presented (?demo=) does not start the tour and does not use up the visitor's first visit", () => {
  const storage = memory();
  assert.equal(autoStart({ store: storage, demoMode: true }), false);
  assert.deepEqual(storage.data, {});
});

test("broken storage does not start the tour and does not throw", () => {
  assert.equal(autoStart({ store: broken, demoMode: false }), false);
});

test("a tap on a view in the menu is recognised, a tap elsewhere is not", () => {
  const inMenu = { closest: (selector: string) => (selector === MENU_LINK ? {} : null) };
  const elsewhere = { closest: () => null };
  assert.equal(choseAView(inMenu), true);
  assert.equal(choseAView(elsewhere), false);
  assert.equal(choseAView(null), false);
});

test("Escape closes the tour only when no other dialog is open to take it", () => {
  assert.equal(escapeClosesTour(0), true);
  assert.equal(escapeClosesTour(1), false);
});
