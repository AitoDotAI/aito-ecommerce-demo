/**
 * Views hidden from the demo until their data is regenerated (ADR 0027).
 *
 * On today's synthetic purchase data these screens contradict themselves
 * or show numbers no retailer would believe (demo review, 2026-09-28).
 * Nothing is deleted: the page code, the API endpoints and the tests stay,
 * and a view comes back by removing its line here.
 *
 * A hidden route still resolves. The shell shows why it is hidden instead
 * of the view, so an old link (the Demand page has been emailed out) does
 * not land on a 404.
 */
// None today: Demand, Markdown and Win-back, hidden here before, are merged
// into Supply and Retention (ADR 0041), and their old routes redirect.
export const HIDDEN_ROUTES: Record<string, string> = {};


/** Why `pathname` is hidden, or undefined if it is shown. Static export
 *  serves routes with a trailing slash ("/demand/"), so that is ignored. */
export function hiddenReason(pathname: string): string | undefined {
  const route = pathname.replace(/\/+$/, "") || "/";
  return HIDDEN_ROUTES[route];
}
