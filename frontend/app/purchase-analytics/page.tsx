"use client";

import { useEffect, useState } from "react";

import { apiFetch, fmtEur } from "@/lib/api";
import { purchaseAnalyticsPanel } from "@/lib/panel-content";
import { usePagePanel } from "@/components/shell/ShellState";
import ErrorState from "@/components/shell/ErrorState";
import type { AnalyticsResponse } from "@/lib/types";


/**
 * Purchase Analytics — month-over-month + segment KPIs + top products
 * + per-segment category mix. Read-heavy, cached 30 min.
 */
export default function PurchaseAnalyticsPage() {
  usePagePanel(purchaseAnalyticsPanel(), {
    title: "Purchase Analytics",
    description:
      "Aggregate analytics across the 24-month window. The data the " +
      "predictions are built on — same dataset, raw counts.",
    breadcrumb: "Purchase Analytics",
  });

  const [data, setData] = useState<AnalyticsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<AnalyticsResponse>("/api/purchase-analytics")
      .then(setData)
      .catch((e) => setError(String(e)));
  }, []);

  if (error) {
    return (
      <div className="fade-in">
        <div className="page-header">
          <div className="page-title">Purchase Analytics</div>
        </div>
        <ErrorState
          title="Couldn't load analytics"
          message={`Aito returned an error. ${error}`}
        />
      </div>
    );
  }

  const maxMonth = data ? Math.max(1, ...data.monthly.map((m) => m.orders)) : 1;
  const maxProd  = data ? Math.max(1, ...data.top_products.map((p) => p.line_count)) : 1;
  const maxSegRev = data ? Math.max(1, ...data.segments.map((s) => s.revenue_eur)) : 1;

  return (
    <div className="fade-in">
      <div className="page-header">
        <div className="page-title">Purchase Analytics</div>
        <div className="page-desc">
          The data the predictions are built on — 24 months of orders +
          12 k baskets aggregated per segment, per category, per month.
        </div>
      </div>

      {/* KPI strip */}
      <div className="kpi-grid">
        <KpiCard
          label="Orders (24 mo)"
          value={data?.segments.reduce((s, x) => s + x.orders, 0)}
          accent="kpi-accent"
        />
        <KpiCard
          label="Revenue (24 mo)"
          value={data?.segments.reduce((s, x) => s + x.revenue_eur, 0)}
          format="eur"
          accent="kpi-accent-green"
        />
        <KpiCard
          label="AOV (overall)"
          value={
            data
              ? Math.round(
                  data.segments.reduce((s, x) => s + x.revenue_eur, 0) /
                    Math.max(1, data.segments.reduce((s, x) => s + x.orders, 0))
                )
              : undefined
          }
          format="eur"
          accent="kpi-accent-blue"
        />
        <KpiCard
          label="Active customers"
          value={data?.segments.reduce((s, x) => s + x.customers, 0)}
          accent="kpi-accent-purple"
        />
      </div>

      <div className="two-col">
        {/* Monthly orders bar list */}
        <div className="card">
          <div className="card-title" style={{ marginBottom: 14 }}>
            Orders per month
            <span style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 400, marginLeft: 6 }}>
              `_search` aggregated
            </span>
          </div>
          {!data && <Skeleton count={6} />}
          <div style={{ maxHeight: 360, overflowY: "auto" }}>
            {data?.monthly.slice().reverse().map((m) => (
              <div className="hbar-row" key={m.month}>
                <div className="hbar-label" style={{ fontFamily: "var(--mono)", fontSize: 12 }}>
                  {m.month}
                </div>
                <div className="hbar-wrap">
                  <div
                    className="hbar"
                    style={{ width: `${(m.orders / maxMonth) * 100}%`, background: "var(--cta)" }}
                  />
                </div>
                <div className="hbar-val">{m.orders}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Top products */}
        <div className="card">
          <div className="card-title" style={{ marginBottom: 14 }}>
            Top 10 products by line count
            <span style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 400, marginLeft: 6 }}>
              all lines
            </span>
          </div>
          {!data && <Skeleton count={6} />}
          {data?.top_products.map((p) => (
            <div className="hbar-row" key={p.sku}>
              <div className="hbar-label" style={{ width: 180 }}>
                <div style={{ fontSize: 12, fontWeight: 600 }}>{p.name}</div>
                <div style={{ fontSize: 10, color: "var(--text-muted)" }}>
                  {p.pet_type} · {p.category}
                </div>
              </div>
              <div className="hbar-wrap">
                <div
                  className="hbar"
                  style={{ width: `${(p.line_count / maxProd) * 100}%`, background: "var(--green)" }}
                />
              </div>
              <div className="hbar-val">{p.line_count}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="two-col">
        {/* Segment KPIs */}
        <div className="card">
          <div className="card-title" style={{ marginBottom: 14 }}>
            Revenue by segment
            <span style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 400, marginLeft: 6 }}>
              avg basket per segment
            </span>
          </div>
          {!data && <Skeleton count={5} />}
          {data?.segments.map((s) => (
            <div className="hbar-row" key={s.segment}>
              <div className="hbar-label" style={{ width: 160 }}>
                <div style={{ fontSize: 12, fontWeight: 600 }}>{s.label}</div>
                <div style={{ fontSize: 10, color: "var(--text-muted)" }}>
                  AOV {fmtEur(s.avg_basket_eur)} · {s.customers} customers
                </div>
              </div>
              <div className="hbar-wrap">
                <div
                  className="hbar"
                  style={{ width: `${(s.revenue_eur / maxSegRev) * 100}%`, background: "var(--blue)" }}
                />
              </div>
              <div className="hbar-val">{fmtEur(s.revenue_eur)}</div>
            </div>
          ))}
        </div>

        {/* Per-segment category mix */}
        <div className="card">
          <div className="card-title" style={{ marginBottom: 14 }}>
            Top categories per segment
            <span style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 400, marginLeft: 6 }}>
              line-count share within segment
            </span>
          </div>
          {!data && <Skeleton count={5} />}
          {data?.category_mix_by_segment.map((row) => (
            <div key={row.segment} style={{ marginBottom: 14 }}>
              <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>{row.label}</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
                {row.top_categories.map((c) => (
                  <span
                    key={`${c.pet_type}.${c.category}`}
                    className="pill pill-grey"
                    style={{ fontSize: 11 }}
                  >
                    {c.pet_type}·{c.category} · {c.share_pct.toFixed(0)}%
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
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


function Skeleton({ count }: { count: number }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          style={{
            height: 28,
            background: "var(--border-light)",
            borderRadius: 4,
            opacity: 0.6,
          }}
        />
      ))}
    </div>
  );
}
