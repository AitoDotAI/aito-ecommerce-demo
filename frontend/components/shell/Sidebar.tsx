"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useShell } from "./ShellState";
import { NAV } from "@/lib/nav";
import { START_TOUR_EVENT } from "./Tour";
import { useSandboxEnv, withSandbox } from "@/lib/sandbox";

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
        <button type="button" className="tour-link" onClick={() => window.dispatchEvent(new Event(START_TOUR_EVENT))}>
          Take the tour
        </button>
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
