"use client";

import { useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";
import { dashboardPanel } from "@/lib/panel-content";
import { usePagePanel } from "@/components/shell/ShellState";
import type { HealthResponse } from "@/lib/types";

/**
 * Dashboard placeholder.
 *
 * Build-order step 5 will replace this with the real KPI grid,
 * `_relate` lift scores, customer-segment cards, and the
 * predicted-next-purchase table from `predictive-ecommerce-demo.html`
 * lines 564–719. For now it shows the page-header + a health pill
 * so the layout shell is visibly wired end-to-end.
 */
export default function DashboardPage() {
  usePagePanel(dashboardPanel(), {
    title: "Store Intelligence Overview",
    description: "Predictive insights from your purchase data — updated on every query.",
    breadcrumb: "Dashboard",
  });

  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<HealthResponse>("/api/health").then(setHealth).catch((e) => setError(String(e)));
  }, []);

  return (
    <div className="fade-in">
      <div className="page-header">
        <div className="page-title">Store Intelligence Overview</div>
        <div className="page-desc">
          Predictive insights from your purchase data — updated on every query.
        </div>
      </div>

      <div className="card">
        <div className="card-title">Scaffold status</div>
        <div className="card-sub">
          The eight views from <code>TASK.md</code> are routed and the
          shell is wired. Real Dashboard content (KPI tiles,{" "}
          <code>_relate</code> lift bars, segment cards) lands in
          build-order step 5.
        </div>
        <div style={{ marginTop: 14 }}>
          {error && (
            <span className="pill pill-red">Backend unreachable: {error}</span>
          )}
          {!error && health && health.aito_connected && (
            <span className="pill pill-green">● Aito connected</span>
          )}
          {!error && health && !health.aito_connected && (
            <span className="pill pill-amber">● Aito unreachable — check .env</span>
          )}
          {!error && !health && <span className="pill pill-grey">Checking…</span>}
        </div>
      </div>
    </div>
  );
}
