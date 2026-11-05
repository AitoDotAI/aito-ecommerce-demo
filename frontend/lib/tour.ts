/**
 * The first-visit tour's rules, without React so they can be tested without a browser (tests/tour.test.mts).
 *
 * A phone visitor who lands on a deep link sees one view and a ☰ button; the menu with every other view is behind it.
 * The tour is three skippable steps that say what this is, open the menu, and point at the Why. It is shown once.
 * Nothing here depends on this demo, so the other demos can reuse it: give them their own views and storage key.
 */

export const STORAGE_KEY = "ecom.tourSeen";
export const MAX_STEPS = 4;

export interface View { href: string; label: string }
export interface Step { id: "what" | "here" | "menu" | "why"; title: string; text: string }
/** The part of `localStorage` the tour uses. */
export interface Store { getItem(key: string): string | null; setItem(key: string, value: string): void }

/** Whether to start the tour by itself. It does not when storage is missing or throws (a private window, blocked site data):
 *  it could not remember being dismissed, so it would come back on every page. The "Take the tour" link still works then. */
export function shouldAutoStart(store: Store | undefined, key = STORAGE_KEY): boolean {
  if (!store) return false;
  try {
    return store.getItem(key) === null;
  } catch {
    return false;
  }
}

export function markSeen(store: Store | undefined, key = STORAGE_KEY): void {
  try {
    store?.setItem(key, "1");
  } catch {
    // The page works without storage; the tour only loses its memory.
  }
}

/** The view a path belongs to: the longest href it equals or sits under. A static export's trailing slash is ignored. */
export function viewForPath(pathname: string, views: View[]): View | undefined {
  const path = pathname.replace(/\/+$/, "") || "/";
  const matches = views.filter((v) => path === v.href || (v.href !== "/" && path.startsWith(v.href + "/")));
  return matches.sort((a, b) => b.href.length - a.href.length)[0];
}

/** The steps for the page the visitor landed on: a deep link starts with the view they are on, the front page with what this is. */
export function stepsFor({ view, viewCount }: { view: View | undefined; viewCount: number }): Step[] {
  const what = "A demo pet shop on generated data: every number is a live query to Aito.";
  const first: Step = view && view.href !== "/"
    ? { id: "here", title: `You are on ${view.label}`, text: `${what} This is one of ${viewCount} views.` }
    : { id: "what", title: "A shop that decides", text: what };
  return [
    first,
    { id: "menu", title: "All the views are in the menu", text: `There are ${viewCount} views: the shop, how it is run, the evidence. Tap one to open it.` },
    { id: "why", title: "Ask a number why", text: "Click a ? beside a prediction for the query and the evidence behind it. The Aito button shows every query a view ran." },
  ];
}
