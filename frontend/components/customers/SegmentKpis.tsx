"use client";

import { fmtEur } from "@/lib/api";
import type { FunnelCounts, ProfilesSummary, SegmentView } from "@/lib/customer-profiles";

const STEPS: [keyof FunnelCounts, string][] = [
  ["impressions", "Impressions"], ["clicks", "Clicks"], ["carts", "Added to cart"], ["purchases", "Purchases"],
];

/** The figures tab: the segment's profit, margin and churn against everyone, and its showing funnel. */
export default function SegmentKpis({ summary, view }: { summary: ProfilesSummary; view: SegmentView }) {
  const segment = view.segment;
  if (!segment || !view.funnel) return null;
  const all = summary.overall;
  const everyone = view.conditions.length === 0;
  const funnel = view.funnel.selected;
  const allFunnel = view.funnel.all;
  const ci = segment.profit_per_customer_ci;
  const per = segment.profit_per_customer_eur ?? 0;
  const diff = per - (all.profit_per_customer_eur ?? 0);
  const clear = ci && !everyone ? (ci[0] > (all.profit_per_customer_eur ?? 0) || ci[1] < (all.profit_per_customer_eur ?? 0)) : null;
  const d = summary.profit_distribution;
  return (
    <div className="card">
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: 12 }}>
        <Kpi label="Profit per customer" value={fmtEur(per)}
          note={!ci ? `only ${segment.customers} customers: no interval` : `${fmtEur(ci[0])} to ${fmtEur(ci[1])}${everyone ? `, median ${fmtEur(d.median_eur)}` : `, ${diff >= 0 ? "+" : ""}${fmtEur(diff)} vs all${clear ? "" : " (not clearly different)"}`}`} />
        <Kpi label="Profit" value={fmtEur(segment.profit_eur ?? 0)} note={`${Math.round((segment.profit_share ?? 0) * 100)} % of all`} />
        <Kpi label="Gross margin" value={`${Math.round((segment.margin ?? 0) * 100)} %`} note={`all ${Math.round((all.margin ?? 0) * 100)} %`} />
        <Kpi label="Revenue" value={fmtEur(segment.revenue_eur ?? 0)} note="price paid, lines kept" />
        <Kpi label="Churned" value={`${Math.round((segment.churn_rate ?? 0) * 100)} %`} note={`all ${Math.round((all.churn_rate ?? 0) * 100)} %`} />
        {everyone && (
          <>
            <Kpi label="Top tenth earns" value={`${Math.round(d.top_tenth_share * 100)} %`} note="of the profit" />
            <Kpi label="Lose money" value={String(d.losing_money)} note={`of ${d.customers.toLocaleString("en-GB")}`} />
          </>
        )}
      </div>
      <div style={{ marginTop: 16 }}>
        <div className="card-sub" style={{ marginBottom: 6 }}>Showing funnel · identified shoppers, counted</div>
        {STEPS.map(([step, label], i) => {
          const n = funnel[step];
          const rate = i === 0 ? null : n / funnel[STEPS[i - 1][0]];
          const allRate = i === 0 ? null : allFunnel[step] / allFunnel[STEPS[i - 1][0]];
          return (
            <div key={step} style={{ margin: "6px 0" }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 12, fontSize: 13 }}>
                <span style={{ fontWeight: 600, whiteSpace: "nowrap" }}>{label}</span>
                <span style={{ fontFamily: "var(--mono)", textAlign: "right" }}>
                  <span style={{ whiteSpace: "nowrap" }}>{n.toLocaleString("en-GB")}</span>
                  {rate !== null && allRate !== null && (
                    <span className="card-sub"> · {Math.round(rate * 100)} % of the step before{everyone ? "" : `, all ${Math.round(allRate * 100)} %`}</span>
                  )}
                </span>
              </div>
              <div style={{ height: 8, background: "var(--border-light)", borderRadius: 3 }}>
                <div style={{ height: 8, width: `${(n / funnel.impressions) * 100}%`, background: "var(--aito-teal)", borderRadius: 3 }} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Kpi({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div>
      <div className="card-sub">{label}</div>
      <div style={{ fontSize: 22, fontWeight: 700 }}>{value}</div>
      <div className="card-sub">{note}</div>
    </div>
  );
}
