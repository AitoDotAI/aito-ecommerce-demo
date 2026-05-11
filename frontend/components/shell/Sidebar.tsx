"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useShell } from "./ShellState";

interface NavItem {
  href: string;
  label: string;
  icon: string;
  badge?: { text: string; tone?: "default" | "green" };
}
interface NavSection {
  label: string;
  items: NavItem[];
}

/**
 * Sidebar navigation — sections in order from
 * `predictive-ecommerce-demo.html` lines 514–560. Active item gets
 * the warm-yellow `--cta` left border.
 *
 * Badges are static placeholders that match the mock. They become
 * data-driven (today's pending counts, current accuracy, etc.)
 * as each view's data layer lands.
 */
const SECTIONS: NavSection[] = [
  {
    label: "Overview",
    items: [
      { href: "/", label: "Dashboard", icon: "📊" },
    ],
  },
  {
    label: "Assist Customers",
    items: [
      { href: "/smart-search",     label: "Smart Search",     icon: "🔍" },
      { href: "/recommendations",  label: "For You",          icon: "✨", badge: { text: "Live" } },
      { href: "/bought-together",  label: "Bought Together",  icon: "🛒" },
    ],
  },
  {
    label: "Analyze",
    items: [
      { href: "/purchase-analytics", label: "Purchase Analytics", icon: "📈" },
      { href: "/pattern-explorer",   label: "Pattern Explorer",   icon: "🔗" },
    ],
  },
  {
    label: "Automate",
    items: [
      { href: "/product-filling", label: "Product Filling", icon: "⚡", badge: { text: "98%", tone: "green" } },
      { href: "/evaluation",      label: "Evaluation",      icon: "🧪" },
    ],
  },
];


export default function Sidebar() {
  const pathname = usePathname();
  const { sidebarCollapsed, mobileOpen, closeMobile, toggleSidebar } = useShell();

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
    <>
    {/* Mid-edge collapse tab — vertically centred on the sidebar's
        right edge, mirror of the Aito panel's left-edge tab. */}
    <button
      type="button"
      className={`sidebar-toggle${sidebarCollapsed ? " collapsed" : ""}`}
      onClick={toggleSidebar}
      aria-label={sidebarCollapsed ? "Open sidebar" : "Close sidebar"}
      title={sidebarCollapsed ? "Open sidebar" : "Close sidebar"}
    >
      {sidebarCollapsed ? "›" : "‹"}
    </button>

    <nav className={classes} aria-label="Main navigation">
      {/* Persona tag — the dataset's identity sits one level below
          the family brand in the topbar ("Predictive E-commerce").
          Mirrors aito-erp-demo's `NavBar__brandTag` placement. */}
      <div className="sidebar-brand-tag">
        <span className="sidebar-brand-name">PetNord</span>
        <span className="sidebar-brand-dim">· Nordic pet store</span>
      </div>

      {SECTIONS.map((section) => (
        <div className="nav-section" key={section.label}>
          <div className="nav-section-label">{section.label}</div>
          {section.items.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`nav-item${isActive(item.href) ? " active" : ""}`}
              onClick={() => closeMobile()}
            >
              <span className="icon" aria-hidden="true">{item.icon}</span>
              {item.label}
              {item.badge && (
                <span className={`nav-badge${item.badge.tone === "green" ? " green" : ""}`}>
                  {item.badge.text}
                </span>
              )}
            </Link>
          ))}
        </div>
      ))}

      <hr className="nav-divider" />

      <div className="sidebar-footer">
        <div className="aito-badge">
          <div className="aito-dot" />
          <div>
            <strong>aito.ai</strong> · Predictive DB
            <br />
            <span style={{ fontSize: 10 }}>11,970 orders · 16ms avg</span>
          </div>
        </div>
      </div>
    </nav>
    </>
  );
}
