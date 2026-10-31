"use client";

import { fmtEur } from "@/lib/api";
import { ACTION_TITLE, TRAITS, TRAIT_TITLE, type ProfilesSummary, type ResponseCell, type Segment } from "@/lib/customer-profiles";
import SegmentBuys from "@/components/customers/SegmentBuys";
import SegmentRelations from "@/components/customers/SegmentRelations";

function find(summary: ProfilesSummary, key: string): { segment: Segment; trait: string } | null {
  for (const trait of TRAITS) {
    const segment = summary.by_trait[trait].find((s) => (s.key ?? `${trait}:${s.value}`) === key);
    if (segment) return { segment, trait };
  }
  return null;
}

/** The selected segment: how it compares with everyone, how it relates to the other variables, what it buys, how it responds. */
export default function SegmentDetail({ summary, selected }: { summary: ProfilesSummary; selected: string }) {
  const found = find(summary, selected);
  const per = found?.segment.profit_per_customer_eur;
  if (!found || per === undefined) {
    return <div className="card card-sub">Select a segment in the list.</div>;
  }
  const { segment, trait } = found;
  const all = { per: summary.profiled_profit_eur / summary.profiled, margin: summary.gross_margin };
  return (
    <div style={{ display: "grid", gap: 12 }}>
      <div className="card">
        <div className="card-title">{TRAIT_TITLE[trait]}: {segment.value}</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", gap: 10 }}>
          <Kpi label="Profit per customer" value={fmtEur(per)} note={`${vs(per - all.per, "€")} vs all`} />
          <Kpi label="Profit" value={fmtEur(segment.profit_eur ?? 0)} note={`${Math.round((segment.profit_share ?? 0) * 100)} % of all`} />
          <Kpi label="Gross margin" value={`${Math.round((segment.margin ?? 0) * 100)} %`}
            note={`${vs(((segment.margin ?? 0) - all.margin) * 100, " pts")} vs all`} />
          <Kpi label="Revenue" value={fmtEur(segment.revenue_eur ?? 0)} note={`${Math.round((segment.revenue_share ?? 0) * 100)} % of all`} />
          <Kpi label="Churned" value={`${Math.round((segment.churn_rate ?? 0) * 100)} %`} note={`${segment.customers} customers`} />
        </div>
      </div>
      <SegmentRelations summary={summary} selected={selected} />
      <SegmentBuys summary={summary} selected={selected} />
      <Response summary={summary} selected={selected} />
    </div>
  );
}

function vs(diff: number, unit: string): string {
  const rounded = Math.round(diff * 10) / 10;
  return `${rounded > 0 ? "+" : ""}${unit === "€" ? rounded.toFixed(0) + " €" : rounded + unit}`;
}

function Kpi({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div>
      <div className="card-sub">{label}</div>
      <div style={{ fontSize: 20, fontWeight: 700 }}>{value}</div>
      <div className="card-sub">{note}</div>
    </div>
  );
}

function shade(cell: ResponseCell, clear: boolean | null, lift: number | null) {
  if (cell.thin || lift === null) return { color: "var(--text-muted)" };
  if (!clear) return { background: "var(--border-light)" };
  return { background: lift > 0 ? "rgba(0, 168, 150, 0.28)" : "rgba(220, 80, 60, 0.25)" };
}

function Response({ summary, selected }: { summary: ProfilesSummary; selected: string }) {
  const entry = summary.response[selected];
  if (!entry) return null;
  return (
    <div className="card">
      <div className="card-title">What the shop&apos;s actions did for them</div>
      <div className="card-sub" style={{ marginBottom: 8, lineHeight: 1.5 }}>
        Observed in the shop&apos;s action table (simulated), against no action in this segment ({entry.none.rows} rows,
        {entry.none.order_rate === null ? "" : ` ${Math.round(entry.none.order_rate * 100)} % ordered,`} {entry.none.profit_eur === null ? "" : `${fmtEur(entry.none.profit_eur, 2)} profit per row`}).
        Orders: points more or fewer who ordered within 30 days. Profit: the 30-day spend at the shop&apos;s {Math.round(summary.gross_margin * 100)} % gross margin
        less the action&apos;s cost, per row. Shaded: larger than its 95 % margin; about one cell in twenty passes by chance. A difference does
        not prove the action caused the order.
      </div>
      <table style={{ width: "100%", fontSize: 13, borderCollapse: "separate", borderSpacing: 3, textAlign: "center" }}>
        <thead><tr className="card-sub"><th style={{ textAlign: "left" }}> </th><th>Rows</th><th>Orders, points</th><th>Profit per row</th></tr></thead>
        <tbody>
          {Object.keys(ACTION_TITLE).map((a) => {
            const c = entry.actions[a];
            return (
              <tr key={a}>
                <td style={{ textAlign: "left" }}>{ACTION_TITLE[a]}</td>
                <td className="card-sub">{c.rows}</td>
                <td style={{ borderRadius: 4, padding: "3px 6px", ...shade(c, c.clear, c.lift_points) }}>
                  {c.lift_points === null ? "–" : <>{c.lift_points > 0 ? "+" : ""}{c.lift_points}<span className="card-sub"> ±{c.margin_points}</span></>}
                </td>
                <td style={{ borderRadius: 4, padding: "3px 6px", ...shade(c, c.profit_clear, c.profit_lift_eur) }}>
                  {c.profit_lift_eur === null ? "–" : <>{c.profit_lift_eur > 0 ? "+" : ""}{fmtEur(c.profit_lift_eur, 2)}<span className="card-sub"> ±{c.profit_margin_eur}</span></>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
