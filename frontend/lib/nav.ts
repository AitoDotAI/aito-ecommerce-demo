/** The site's views, as the sidebar lists them and the first-visit tour counts them (lib/tour.ts). */

export interface NavItem {
  href: string;
  label: string;
  icon: string;
  /** Evidence entries say which data they rest on (ADR 0037). */
  data?: "Real" | "Synthetic";
}
export interface NavGroup {
  /** Left out when the group is its heading's only theme (Evidence). */
  label?: string;
  items: NavItem[];
}
export interface NavHeading {
  label: string;
  groups: NavGroup[];
}

/**
 * The site's two halves (ADR 0037) and its groups, one per person
 * (ADR 0041): the shopper, the owner, the operator, the evaluator, the
 * developer. Each entry is one job.
 */
export const NAV: NavHeading[] = [
  {
    label: "360° intelligent ecommerce",
    groups: [
      {
        label: "Shop",
        items: [
          { href: "/shop", label: "Shop", icon: "🛍️" },
        ],
      },
      {
        label: "Run the shop",
        items: [
          { href: "/",                 label: "Overview",  icon: "📊" },
          { href: "/patterns",         label: "Patterns",  icon: "🔗" },
          { href: "/product",          label: "Product",   icon: "🏷️" },
          { href: "/reviews",          label: "Reviews",   icon: "⭐" },
          { href: "/acquisition",      label: "Acquisition", icon: "🧲" },
          { href: "/supply",           label: "Supply",    icon: "📦" },
          { href: "/retention",        label: "Retention", icon: "🔁" },
          { href: "/customers",        label: "Analytics", icon: "📈" },
        ],
      },
      {
        label: "Operate",
        items: [
          { href: "/product-filling", label: "Product filling", icon: "⚡" },
          { href: "/review-triage",   label: "Review triage",   icon: "💬" },
          { href: "/shopkeeper",      label: "Shopkeeper",      icon: "🤖" },
          { href: "/experiments",     label: "Experiments",     icon: "🧪" },
        ],
      },
    ],
  },
  {
    label: "Evidence",
    groups: [
      {
        items: [
          { href: "/evidence",                      label: "Index",               icon: "📋" },
          { href: "/evidence/business-reorders",    label: "Business reorders",   icon: "🧾", data: "Real" },
          { href: "/evidence/personalised-search",  label: "Personalised search", icon: "🔍", data: "Synthetic" },
          { href: "/evidence/search-relevance",     label: "Search relevance",    icon: "🎯", data: "Synthetic" },
          { href: "/evidence/model-checks",         label: "Model checks",        icon: "🧪", data: "Synthetic" },
        ],
      },
      {
        label: "For developers",
        items: [
          { href: "/query-patterns", label: "Query patterns", icon: "⌨️" },
        ],
      },
    ],
  },
];

export const VIEWS = NAV.flatMap((heading) => heading.groups.flatMap((group) => group.items.map(({ href, label }) => ({ href, label }))));
