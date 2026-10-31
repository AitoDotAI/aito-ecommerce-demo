"use client";

import { useState } from "react";

import { fmtEur } from "@/lib/api";
import { TRAITS, TRAIT_TITLE, type ProfilesSummary, type Segment } from "@/lib/customer-profiles";

type Row = Segment & { key: string; trait: string };

/** Every segment in one list with its key figures, profit first. Select one to inspect it. */
export default function SegmentList({ summary, selected, onSelect }: {
  summary: ProfilesSummary; selected: string; onSelect: (key: string) => void;
}) {
  const [grouped, setGrouped] = useState(true);
  const rows: Row[] = TRAITS.flatMap((trait) => summary.by_trait[trait]
    .filter((s) => s.profit_per_customer_eur !== undefined)
    .map((s) => ({ ...s, key: s.key ?? `${trait}:${s.value}`, trait })));
  const overall = summary.profiled_profit_eur / summary.profiled;
  const scale = Math.max(...rows.map((r) => r.profit_per_customer_eur ?? 0), overall);
  const sorted = [...rows].sort((a, b) => (b.profit_per_customer_eur ?? 0) - (a.profit_per_customer_eur ?? 0));
  const shared = { selected, onSelect, scale, overall };
  return (
    <div className="card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
        <div className="card-title" style={{ margin: 0 }}>Compare all segments · {rows.length}</div>
        <span style={{ display: "inline-flex", gap: 4 }}>
          {([[true, "By variable"], [false, "By profit per customer"]] as const).map(([g, label]) => (
            <button key={label} aria-pressed={grouped === g} onClick={() => setGrouped(g)} style={{
              cursor: "pointer", borderRadius: 12, padding: "2px 10px", font: "inherit", fontSize: 12, color: "var(--text)",
              border: `1px solid ${grouped === g ? "var(--aito-teal)" : "var(--border)"}`,
              background: grouped === g ? "rgba(0, 168, 150, 0.15)" : "transparent" }}>{label}</button>
          ))}
        </span>
      </div>
      <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse", marginTop: 8 }}>
        <thead>
          <tr className="card-sub" style={{ textAlign: "right" }}>
            <th style={{ textAlign: "left" }}> </th><th style={{ paddingLeft: 8 }}>Customers</th>
            <th style={{ textAlign: "left", paddingLeft: 10 }}>Profit per customer</th><th style={{ paddingLeft: 8 }}>Profit</th><th style={{ paddingLeft: 8 }}>Churned</th>
          </tr>
        </thead>
        <tbody>
          {grouped
            ? TRAITS.map((trait) => (
                <Group key={trait} title={TRAIT_TITLE[trait]} rows={rows.filter((r) => r.trait === trait)} {...shared} />))
            : <Group rows={sorted} showTrait {...shared} />}
        </tbody>
      </table>
      <div className="card-sub" style={{ marginTop: 8, lineHeight: 1.5 }}>
        Profit: price paid less unit cost on the lines kept (returned lines earn nothing), less the shop&apos;s action costs; no delivery
        or payment cost is in the data. Unit cost is the inventory&apos;s current cost per product (about two-thirds of the base price)
        applied to two years of sales, and 165 kept lines were sold below it. ± is half the 95 % bootstrap interval of profit per
        customer: a few customers earn much of it. The line marks the average profiled customer, {fmtEur(overall)}. Pets and diets
        overlap. Faded: under 30 customers.
      </div>
    </div>
  );
}

function Group({ title, rows, selected, onSelect, scale, overall, showTrait }: {
  title?: string; rows: Row[]; selected: string; onSelect: (key: string) => void; scale: number; overall: number; showTrait?: boolean;
}) {
  return (
    <>
      {title && <tr><td colSpan={5} style={{ paddingTop: 10, fontWeight: 600, fontSize: 12, color: "var(--text-muted)" }}>{title}</td></tr>}
      {rows.map((r) => {
        const per = r.profit_per_customer_eur ?? 0;
        const on = r.key === selected;
        return (
          <tr key={r.key} onClick={() => onSelect(r.key)} style={{ cursor: "pointer", textAlign: "right", opacity: r.thin ? 0.55 : 1,
            background: on ? "rgba(0, 168, 150, 0.14)" : undefined, outline: on ? "1px solid var(--aito-teal)" : undefined }}>
            <td style={{ textAlign: "left", padding: "3px 4px" }}>
              {showTrait && <span className="card-sub">{TRAIT_TITLE[r.trait]}: </span>}{r.value}
            </td>
            <td style={{ whiteSpace: "nowrap", paddingLeft: 8 }}><span title={`${Math.round(r.share * 100)} % of profiled customers`}>{r.customers.toLocaleString("fi-FI")}</span></td>
            <td style={{ textAlign: "left", paddingLeft: 10, whiteSpace: "nowrap" }}>
              <span style={{ display: "inline-block", position: "relative", width: 56, height: 8, background: "var(--border-light)", borderRadius: 2, marginRight: 6 }}>
                <span style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: `${(per / scale) * 100}%`, background: "var(--aito-teal)", borderRadius: 2 }} />
                <span style={{ position: "absolute", left: `${(overall / scale) * 100}%`, top: -2, bottom: -2, width: 1, background: "var(--text)" }} />
              </span>
              <strong title={r.profit_per_customer_ci ? `95 % interval ${fmtEur(r.profit_per_customer_ci[0])} to ${fmtEur(r.profit_per_customer_ci[1])}` : `only ${r.customers} customers: no interval`}>{fmtEur(per)}</strong>
              {r.profit_per_customer_ci
                ? <span className="card-sub"> ±{Math.round((r.profit_per_customer_ci[1] - r.profit_per_customer_ci[0]) / 2)}</span>
                : <span className="card-sub"> n={r.customers}</span>}
            </td>
            <td style={{ whiteSpace: "nowrap", paddingLeft: 8 }}><span title={`${Math.round((r.profit_share ?? 0) * 100)} % of the profiled customers' profit`}>{fmtEur(r.profit_eur ?? 0)}</span></td>
            <td style={{ paddingLeft: 8 }}>{r.churn_rate === undefined ? "–" : `${Math.round(r.churn_rate * 100)} %`}</td>
          </tr>
        );
      })}
    </>
  );
}
