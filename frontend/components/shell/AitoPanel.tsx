"use client";

import { useShell } from "./ShellState";

/**
 * Right-rail Aito panel — locked colours / structure per
 * `aito-demo-framework.md §5.3` and ADR 0004. Pages set their
 * `AitoPanelConfig` via `usePagePanel(...)`; this component
 * renders whatever's currently in shell state.
 *
 * Stats above the body block are pinned. Body scrolls. CTA pinned
 * to the bottom — the "Start free trial" button is always reachable.
 *
 * Matches `predictive-ecommerce-demo.html` lines 195–309 + 1462–1515.
 */
export default function AitoPanel() {
  const { aitoCollapsed, mobileOpen, panel, toggleAito } = useShell();

  const classes = [
    "aito-panel",
    aitoCollapsed ? "collapsed" : "",
    mobileOpen === "aito" ? "mobile-open" : "",
  ].filter(Boolean).join(" ");

  const KNOWN_ENDPOINTS = ["_predict", "_recommend", "_relate", "_evaluate"];
  const activeEndpoints = panel?.endpoints ?? [];

  // Pinned set of demo-wide stats. Pages can override via
  // `config.stats`; we fall back to a brand-strip default so the
  // panel header never reads empty.
  const stats = panel?.stats ?? [
    { label: "Orders",  value: "11.9k" },
    { label: "p50 ms",  value: "12" },
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
          {/* Active endpoints first (teal), then the rest greyed (purple) */}
          {activeEndpoints.map((ep) => (
            <span className="aito-tag active" key={ep}>{ep}</span>
          ))}
          {KNOWN_ENDPOINTS
            .filter((e) => !activeEndpoints.includes(e))
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
    </aside>
    </>
  );
}
