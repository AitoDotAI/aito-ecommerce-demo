"use client";

import LatencyBadge from "./LatencyBadge";
import { useShell } from "./ShellState";


/** Adds `aito-collapsed` to the topbar when the Aito panel is hidden
 *  so the topbar's right edge expands to the viewport's. */
function topbarClass(aitoCollapsed: boolean): string {
  return aitoCollapsed ? "topbar aito-collapsed" : "topbar";
}

/**
 * Topbar — brand sits in the sidebar-width slot on the left,
 * breadcrumb + actions on the right. Hamburger toggles the
 * sidebar; lightning toggles the Aito side panel.
 *
 * Matches `predictive-ecommerce-demo.html` lines 481–505 exactly.
 */
export default function TopBar() {
  const { sidebarCollapsed, aitoCollapsed, breadcrumb, toggleSidebar } = useShell();

  return (
    <div className={topbarClass(aitoCollapsed)}>
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
        <div className="brand-text">
          {/* Family line — matches "Predictive ERP" / "Predictive Ledger"
              from the sibling demos. PetNord is the dataset/persona and
              gets a chip in the sidebar (see Sidebar's brand-tag).
              Two-span layout forces the break between the two words
              cleanly across desktop + narrow viewports, regardless of
              the brand slot's width. */}
          <div className="store-name">
            <span className="store-name-line">Predictive</span>
            <span className="store-name-line">E-commerce</span>
          </div>
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
          {/* The Aito-panel toggle used to live here. It moved to the
              mid-edge tab on the panel itself (see AitoPanel's
              `aito-panel-toggle`) — same affordance as the accounting
              demo. */}
          <div className="avatar" aria-hidden="true">PN</div>
        </div>
      </div>
    </div>
  );
}
