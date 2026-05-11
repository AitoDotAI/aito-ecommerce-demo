"use client";

import LatencyBadge from "./LatencyBadge";
import { useShell } from "./ShellState";

/**
 * Topbar — brand sits in the sidebar-width slot on the left,
 * breadcrumb + actions on the right. Hamburger toggles the
 * sidebar; lightning toggles the Aito side panel.
 *
 * Matches `predictive-ecommerce-demo.html` lines 481–505 exactly.
 */
export default function TopBar() {
  const { sidebarCollapsed, aitoCollapsed, breadcrumb, toggleSidebar, toggleAito } = useShell();

  return (
    <div className="topbar">
      <div className="topbar-brand">
        <button
          type="button"
          className={`toggle-btn${sidebarCollapsed ? " active" : ""}`}
          onClick={toggleSidebar}
          title="Toggle navigation"
          aria-label="Toggle navigation"
        >
          ☰
        </button>
        <div className="logo-mark" aria-hidden="true">
          <span>🐾</span>
        </div>
        <div>
          <div className="store-name">PetNord</div>
          <div className="store-sub">Powered by aito.ai</div>
        </div>
      </div>

      <div className="topbar-content">
        <div className="breadcrumb">
          <span>E-Commerce</span>
          <span className="sep">›</span>
          <span className="current">{breadcrumb}</span>
        </div>
        <div className="topbar-actions">
          <LatencyBadge />
          <button type="button" className="btn btn-ghost">Export</button>
          <a
            className="btn btn-primary"
            href="https://aito.ai"
            target="_blank"
            rel="noopener noreferrer"
          >
            Live Demo
          </a>
          <button
            type="button"
            className={`toggle-btn toggle-btn-aito${aitoCollapsed ? " active" : ""}`}
            onClick={toggleAito}
            title="Toggle Aito panel"
            aria-label="Toggle Aito panel"
          >
            ⚡
          </button>
          <div className="avatar" aria-hidden="true">PN</div>
        </div>
      </div>
    </div>
  );
}
