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
export const HIDDEN_ROUTES: Record<string, string> = {
  "/demand":
    "The forecast is being re-measured against the naive " +
    "“same as last month” forecast, on regenerated purchase data.",
  "/winback":
    "It showed a raw purchase probability as a campaign response rate (96 %).",
  "/markdown":
    "Its proposals lost margin on every row with today's synthetic prices.",
  "/price":
    "It opened on a price point backed by only two sales.",
  "/cart-completion":
    "Its suggestions ignored basket size (a €108 bag for a €1.68 cart).",
};


/** Why `pathname` is hidden, or undefined if it is shown. Static export
 *  serves routes with a trailing slash ("/demand/"), so that is ignored. */
export function hiddenReason(pathname: string): string | undefined {
  const route = pathname.replace(/\/+$/, "") || "/";
  return HIDDEN_ROUTES[route];
}
