"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useShell } from "./ShellState";
import { useSandboxEnv, withSandbox } from "@/lib/sandbox";

interface NavItem {
  href: string;
  label: string;
  icon: string;
  /** Evidence entries say which data they rest on (ADR 0037). */
  data?: "Real" | "Synthetic";
}
interface NavGroup {
  /** Left out when the group is its heading's only theme (Evidence). */
  label?: string;
  items: NavItem[];
}
interface NavHeading {
  label: string;
  groups: NavGroup[];
}

/**
 * The site's two halves (ADR 0037) and its groups, one per person
 * (ADR 0041): the shopper, the owner, the operator, the evaluator, the
 * developer. Each entry is one job.
 */
const NAV: NavHeading[] = [
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
        ],
      },
      {
        label: "Operate",
        items: [
          { href: "/product-filling", label: "Product filling", icon: "⚡" },
          { href: "/review-triage",   label: "Review triage",   icon: "💬" },
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


export default function Sidebar() {
  const pathname = usePathname();
  const { sidebarCollapsed, mobileOpen, closeMobile } = useShell();
  const sandbox = useSandboxEnv();   // sandbox mode: every view keeps ?db (ADR 0043)

  const isActive = (href: string) => {
    if (href === "/") return pathname === "/" || pathname === "";
    return pathname === href || pathname === href + "/";
  };

  const classes = [
    "sidebar",
    sidebarCollapsed ? "collapsed" : "",
    mobileOpen === "sidebar" ? "mobile-open" : "",
  ].filter(Boolean).join(" ");

  return (
    <nav className={classes} aria-label="Main navigation">
      {/* Persona tag — the dataset's identity sits one level below
          the family brand in the topbar ("Predictive E-commerce").
          Mirrors aito-erp-demo's `NavBar__brandTag` placement. */}
      <div className="sidebar-brand-tag">
        <span className="sidebar-brand-name">PetNord</span>
        <span className="sidebar-brand-dim">· Nordic pet store</span>
      </div>

      {NAV.map((heading) => (
        <div className="nav-heading" key={heading.label}>
          <div className="nav-heading-label">{heading.label}</div>
          {heading.groups.map((group, i) => (
            <div className="nav-section" key={group.label ?? i}>
              {group.label && <div className="nav-section-label">{group.label}</div>}
              {group.items.map((item) => (
                <Link
                  key={item.href}
                  href={withSandbox(item.href, sandbox)}
                  className={`nav-item${isActive(item.href) ? " active" : ""}`}
                  onClick={() => closeMobile()}
                >
                  <span className="icon" aria-hidden="true">{item.icon}</span>
                  {item.label}
                  {item.data && (
                    <span className={`nav-data-mark${item.data === "Real" ? " real" : ""}`}
                          title={`${item.data} data`}>
                      {item.data}
                    </span>
                  )}
                </Link>
              ))}
            </div>
          ))}
        </div>
      ))}

      <hr className="nav-divider" />

      <div className="sidebar-footer">
        <div className="aito-badge">
          <div className="aito-dot" />
          <div>
            <strong>aito.ai</strong> · Predictive DB
          </div>
        </div>
      </div>
    </nav>
  );
}
