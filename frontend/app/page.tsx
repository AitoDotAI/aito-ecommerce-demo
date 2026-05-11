"use client";

import { useEffect, useState } from "react";

import { apiFetch, fmtEur } from "@/lib/api";
import { dashboardPanel } from "@/lib/panel-content";
import { usePagePanel } from "@/components/shell/ShellState";
import LiftHint from "@/components/prediction/LiftHint";
import ErrorState from "@/components/shell/ErrorState";
import type { DashboardResponse } from "@/lib/types";

/**
 * Dashboard view — KPI grid + top purchase patterns + customer
 * segments + insight tip + recent orders. Data layer is
 * `src/overview_service.py`; see `docs/adr/0005-dashboard.md` for
 * the live-vs-Python split (top patterns are computed locally;
 * everything else hits Aito live).
 */
export default function DashboardPage() {
  usePagePanel(dashboardPanel(), {
    title: "Store Intelligence Overview",
    description: "Predictive insights from your purchase data — updated on every query.",
    breadcrumb: "Dashboard",
  });

  const [data, setData] = useState<DashboardResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<DashboardResponse>("/api/dashboard")
      .then(setData)
      .catch((e) => setError(String(e)));
  }, []);

  if (error) {
    return (
      <div className="fade-in">
        <div className="page-header">
          <div className="page-title">Store Intelligence Overview</div>
          <div className="page-desc">
            Predictive insights from your purchase data — updated on every query.
          </div>
        </div>
        <ErrorState
          title="Couldn't load the dashboard"
          message={`Aito returned an error. ${error}`}
          command="./do load-data"
        />
      </div>
    );
  }

  return (
    <div className="fade-in">
      <div className="page-header">
        <div className="page-title">Store Intelligence Overview</div>
        <div className="page-desc">
          Predictive insights from your purchase data — updated on every query.
        </div>
      </div>

      {/* KPI grid */}
      <div className="kpi-grid">
        <KpiCard label="Products"        value={data?.kpis.products.value}        accent="kpi-accent" />
        <KpiCard label="Orders (12mo)"   value={data?.kpis.orders_12mo.value}     accent="kpi-accent-green" />
        <KpiCard label="Customers"       value={data?.kpis.customers.value}       accent="kpi-accent-blue" />
        <KpiCard
          label="Avg. Basket"
          value={data?.kpis.avg_basket_eur.value}
          format="eur"
          accent="kpi-accent-purple"
        />
      </div>

      {/* Two-column: top patterns + segments */}
      <div className="two-col">
        <div className="card">
          <div className="card-title" style={{ marginBottom: 14 }}>
            Top Purchase Patterns
            <span style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 400, marginLeft: 6 }}>
              _relate · lift scores
            </span>
          </div>
          {!data && <SkeletonLines count={6} />}
          {data?.top_patterns.map((p) => (
            <div className="lift-row" key={p.label}>
              <div className="lift-label">{p.label}</div>
              <div className="lift-bar-wrap">
                <div className="lift-bar" style={{ width: `${p.bar_pct}%` }} />
              </div>
              <LiftHint value={p.lift} />
            </div>
          ))}
        </div>

        <div className="card">
          <div className="card-title" style={{ marginBottom: 14 }}>
            Customer Segments
            <span style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 400, marginLeft: 6 }}>
              live `_search` per segment
            </span>
          </div>
          {!data && <SkeletonLines count={4} />}
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {data?.segments.map((seg) => (
              <div
                key={seg.id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  padding: 10,
                  background: "var(--bg)",
                  borderRadius: 8,
                }}
              >
                <span style={{ fontSize: 20 }} aria-hidden="true">{seg.emoji}</span>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 600 }}>{seg.label}</div>
                  <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                    {seg.share_pct}% of buyers · avg {fmtEur(seg.avg_basket_eur)} / order · {seg.note}
                  </div>
                </div>
                <span className={`pill pill-${seg.pill_tone}`}>{seg.pill_text}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Insight tip-box */}
      {data?.insight && (
        <div className="tip-box">
          <span className="tip-icon" aria-hidden="true">💡</span>
          <span
            dangerouslySetInnerHTML={{
              __html: `<strong>${data.insight.headline}:</strong> ${data.insight.body}`,
            }}
          />
        </div>
      )}

      {/* Recent orders */}
      <div className="card">
        <div className="card-title" style={{ marginBottom: 14 }}>
          Recent Orders
          <span style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 400, marginLeft: 6 }}>
            most recent first · predicted-next column lands with For You
          </span>
        </div>
        <table className="data-table">
          <thead>
            <tr>
              <th>Order</th>
              <th>Customer</th>
              <th>Products</th>
              <th>Month</th>
              <th>Value</th>
            </tr>
          </thead>
          <tbody>
            {!data && (
              <tr>
                <td colSpan={5} style={{ color: "var(--text-muted)", fontSize: 12 }}>
                  Loading…
                </td>
              </tr>
            )}
            {data?.recent_orders.map((o) => (
              <tr key={o.order_id}>
                <td style={{ fontFamily: "var(--mono)", fontSize: 12 }}>{o.order_id}</td>
                <td>{o.customer_short}</td>
                <td>{o.line_summary}</td>
                <td style={{ fontFamily: "var(--mono)", fontSize: 12, color: "var(--text-muted)" }}>
                  {o.month}
                </td>
                <td style={{ fontWeight: 600 }}>{fmtEur(o.total_eur)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}


function KpiCard({
  label,
  value,
  accent,
  format,
}: {
  label: string;
  value: number | undefined;
  accent: string;
  format?: "eur";
}) {
  const display =
    value == null ? "…"
    : format === "eur" ? fmtEur(value)
    : value.toLocaleString("fi-FI");
  return (
    <div className={`kpi-card ${accent}`}>
      <div className="kpi-label">{label}</div>
      <div className="kpi-val">{display}</div>
    </div>
  );
}


function SkeletonLines({ count }: { count: number }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          style={{
            height: 16,
            background: "var(--border-light)",
            borderRadius: 4,
            opacity: 0.6,
          }}
        />
      ))}
    </div>
  );
}
