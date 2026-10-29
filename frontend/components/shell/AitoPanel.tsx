"use client";

import { useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";
import { useShell } from "./ShellState";

/**
 * Right-rail Aito panel — locked colours / structure per
 * `aito-demo-framework.md §5.3` and ADR 0004. Pages set their
 * `AitoPanelConfig` via `usePagePanel(...)`; this component
 * renders whatever's currently in shell state.
 *
 * Stats above the body block are pinned. Body scrolls. CTA pinned
 * to the bottom — the "Start free trial" button is always reachable,
 * except in demo mode (lib/demo-mode.ts), where the room is a meeting.
 *
 * Matches `predictive-ecommerce-demo.html` lines 195–309 + 1462–1515.
 */
export default function AitoPanel() {
  const { aitoCollapsed, mobileOpen, panel, toggleAito, demoMode } = useShell();
  const orders = useOrderCount(panel?.stats === undefined);

  const classes = [
    "aito-panel",
    aitoCollapsed ? "collapsed" : "",
    mobileOpen === "aito" ? "mobile-open" : "",
  ].filter(Boolean).join(" ");

  const KNOWN_ENDPOINTS = ["_predict", "_recommend", "_relate", "_evaluate"];
  const activeEndpoints = panel?.endpoints ?? [];

  // Pinned set of demo-wide stats. Pages can override via `config.stats`; the default
  // is the shop's order count, read from the data (it was a typed "11.9k" that no release
  // matched), and two facts of the setup. No latency here: a typed one would be a made-up number.
  const stats = panel?.stats ?? [
    ...(orders === null ? [] : [{ label: "Orders", value: formatCount(orders) }]),
    { label: "Models",  value: "0" },
    { label: "Hosted",  value: "EU" },
  ];

  return (
    <>
    {/* Mid-edge collapse tab — vertically centred on the panel's left
        edge. When the panel is collapsed it slides to the viewport's
        right edge. Same affordance as accounting.aito.ai's panel. */}
    <button
      type="button"
      className={`aito-panel-toggle${aitoCollapsed ? " collapsed" : ""}`}
      onClick={toggleAito}
      aria-label={aitoCollapsed ? "Open Aito panel" : "Close Aito panel"}
      title={aitoCollapsed ? "Open Aito panel" : "Close Aito panel"}
    >
      {aitoCollapsed ? "‹" : "›"}
    </button>

    {/* Mobile FAB — Aito-logo bubble in the bottom-right that opens
        the panel as an off-canvas drawer. Mirrors the
        accounting-demo's mobile pattern; CSS hides it on desktop. */}
    <button
      type="button"
      className="aito-mobile-fab"
      onClick={toggleAito}
      aria-label={mobileOpen === "aito" ? "Close Aito panel" : "Open Aito panel"}
      aria-expanded={mobileOpen === "aito"}
      title="Aito prediction context"
    >
      <img src="/aito-logo.svg" alt="" className="aito-mobile-fab-icon" />
    </button>

    <aside className={classes} aria-label="Aito prediction context panel">
      <div className="aito-panel-header">
        <img src="/aito-logo.svg" alt="Aito.ai" className="aito-logo-img" />
        <span className="aito-panel-tagline">Predictive DB</span>
      </div>

      <div className="aito-stats">
        {stats.map((stat) => (
          <div className="aito-stat" key={`${stat.label}-${stat.value}`}>
            <div className="aito-stat-val">{stat.value}</div>
            <div className="aito-stat-label">{stat.label}</div>
          </div>
        ))}
      </div>

      <div className="aito-panel-content">
        <div className="aito-panel-title">
          {panel?.operation ?? "Predictive E-commerce"}
        </div>

        <div className="aito-section-title">Endpoints</div>
        <div className="aito-tags">
          {/* The endpoints this page sends. A page that names none gets the
              known ones greyed, so the strip never reads empty. */}
          {activeEndpoints.map((ep) => (
            <span className="aito-tag active" key={ep}>{ep}</span>
          ))}
          {activeEndpoints.length === 0 && KNOWN_ENDPOINTS
            .map((ep) => (
              <span className="aito-tag" key={ep}>{ep}</span>
            ))}
        </div>

        {panel?.description && (
          <div
            className="aito-desc"
            dangerouslySetInnerHTML={{ __html: panel.description }}
          />
        )}

        {panel?.query && (
          <div className="aito-query">
            <pre dangerouslySetInnerHTML={{ __html: panel.query }} />
          </div>
        )}

        {panel?.links && panel.links.length > 0 && (
          <>
            <div className="aito-section-title">Learn More</div>
            {panel.links.map((link) => (
              <a
                key={link.url}
                className="aito-link"
                href={link.url}
                target="_blank"
                rel="noopener noreferrer"
              >
                <span className="aito-link-icon" aria-hidden="true">↗</span>
                {link.label}
              </a>
            ))}
          </>
        )}

        <div style={{ height: 12 }} />
        <div className="aito-section-title">Data</div>
        <div style={{ fontSize: 11, color: "var(--aito-dim)", lineHeight: 1.5 }}>
          EU hosted · No PII stored
        </div>
      </div>

      {!demoMode && (
        <div className="aito-panel-cta">
          <a
            className="aito-cta"
            href="https://aito.ai"
            target="_blank"
            rel="noopener noreferrer"
          >
            Start free trial →
          </a>
        </div>
      )}
    </aside>
    </>
  );
}


/** Orders in the data, from the Overview's totals (a snapshot, so cheap); null until it answers or if it fails. */
function useOrderCount(wanted: boolean): number | null {
  const [orders, setOrders] = useState<number | null>(null);
  useEffect(() => {
    if (!wanted) return;
    apiFetch<{ kpis: { orders: number; orders_before: number } }>("/api/overview")
      .then((o) => setOrders(o.kpis.orders + o.kpis.orders_before))
      .catch(() => setOrders(null));
  }, [wanted]);
  return orders;
}

function formatCount(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n);
}
