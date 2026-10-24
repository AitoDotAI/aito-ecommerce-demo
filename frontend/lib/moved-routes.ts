/**
 * Routes that moved or were dropped when the site was regrouped by job
 * (ADR 0041). Each old route keeps a page that forwards to its new home,
 * so links in posts, emails and the README keep working.
 *
 * The site is a static export, so `next.config` redirects don't run; the
 * forward happens in the browser (`components/shell/MovedRoute.tsx`) and
 * keeps the link's query string.
 */
export interface MovedRoute {
  to: string;
  /** Shown while forwarding, and to a browser without JavaScript. */
  label: string;
}

export const MOVED_ROUTES: Record<string, MovedRoute> = {
  "/shop-analytics":    { to: "/patterns/",                      label: "Patterns" },
  "/business-reorders": { to: "/evidence/business-reorders/",    label: "Evidence › Business reorders" },
  "/evaluation":        { to: "/evidence/model-checks/",         label: "Evidence › Model checks" },
  "/smart-search":      { to: "/evidence/personalised-search/",  label: "Evidence › Personalised search" },
  "/recommendations":   { to: "/query-patterns/",                label: "Query patterns" },
  // Merged views. Pattern Explorer's `?anchor=` is Patterns' anchor
  // filter; Basket Rules' confidence and support are columns on Baskets;
  // Purchase Analytics' trend and best sellers are on the Overview.
  "/pattern-explorer":  { to: "/patterns/",                      label: "Patterns" },
  "/basket-rules":      { to: "/patterns/",                      label: "Patterns" },
  "/purchase-analytics": { to: "/",                              label: "Overview" },
  // Dropped views: their question is answered elsewhere, better measured.
  // Bought Together's category pairs are Patterns › Baskets; Cart
  // Completion's add-ons are the Shop's cart re-ranking "Picked for you".
  "/bought-together":   { to: "/patterns/",                      label: "Patterns" },
  "/cart-completion":   { to: "/shop/",                          label: "the Shop" },
};
