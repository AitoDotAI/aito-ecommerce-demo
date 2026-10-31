"use client";

import { fmtEur } from "@/lib/api";
import { findSegment, type FunnelCounts, type ProfilesSummary } from "@/lib/customer-profiles";

const STEPS: [keyof FunnelCounts, string][] = [
  ["impressions", "Impressions"], ["clicks", "Clicks"], ["carts", "Added to cart"], ["purchases", "Purchases"],
];

/** The top right: the segment's key figures against everyone, and its showing funnel. */
export default function SegmentKpis({ summary, selected }: { summary: ProfilesSummary; selected: string }) {
  const found = findSegment(summary, selected);
  if (!found) return null;
  const { segment } = found;
  const all = summary.overall;
  const funnel = summary.funnel[selected];
  const allFunnel = summary.funnel.all;
  const ci = segment.profit_per_customer_ci;
  const per = segment.profit_per_customer_eur ?? 0;
  const diff = per - (all.profit_per_customer_eur ?? 0);
  const clear = ci && selected !== "all" ? (ci[0] > (all.profit_per_customer_eur ?? 0) || ci[1] < (all.profit_per_customer_eur ?? 0)) : null;
  return (
    <div className="card" style={{ borderTop: "3px solid var(--cta)" }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: 12 }}>
        <Kpi label="Profit per customer" value={segment.customers < 30 || !ci ? `${fmtEur(per)}` : fmtEur(per)}
          note={!ci ? `only ${segment.customers} customers: no interval` : `${fmtEur(ci[0])} to ${fmtEur(ci[1])}${selected === "all" ? `, median ${fmtEur(summary.profit_distribution.median_eur)}` : `, ${diff >= 0 ? "+" : ""}${fmtEur(diff)} vs all${clear ? "" : " (not clearly different)"}`}`} />
        <Kpi label="Profit" value={fmtEur(segment.profit_eur ?? 0)} note={`${Math.round((segment.profit_share ?? 0) * 100)} % of all`} />
        <Kpi label="Gross margin" value={`${Math.round((segment.margin ?? 0) * 100)} %`} note={`all ${Math.round((all.margin ?? 0) * 100)} %`} />
        <Kpi label="Revenue" value={fmtEur(segment.revenue_eur ?? 0)} note="price paid, lines kept" />
        <Kpi label="Churned" value={`${Math.round((segment.churn_rate ?? 0) * 100)} %`} note={`all ${Math.round((all.churn_rate ?? 0) * 100)} %`} />
        {selected === "all" && (
          <>
            <Kpi label="Top tenth earns" value={`${Math.round(summary.profit_distribution.top_tenth_share * 100)} %`} note="of the profit" />
            <Kpi label="Lose money" value={String(summary.profit_distribution.losing_money)} note={`of ${summary.profit_distribution.customers.toLocaleString("en-GB")}`} />
          </>
        )}
      </div>
      {funnel && (
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
                      <span className="card-sub"> · {Math.round(rate * 100)} % of the step before{selected === "all" ? "" : `, all ${Math.round(allRate * 100)} %`}</span>
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
      )}
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
