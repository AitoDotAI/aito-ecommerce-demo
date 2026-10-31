"use client";

import { fmtEur } from "@/lib/api";
import { TRAIT_TITLE, type ProfilesSummary } from "@/lib/customer-profiles";

/** How customers shop, by trait: size, churn and spend of each group. Counts of what they bought, not guesses about them. */
export default function SegmentTables({ summary }: { summary: ProfilesSummary }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 12 }}>
      {(Object.keys(TRAIT_TITLE) as (keyof typeof summary.by_trait)[]).map((trait) => (
        <div key={trait} className="card">
          <div className="card-title">{TRAIT_TITLE[trait]}</div>
          <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
            <thead>
              <tr className="card-sub" style={{ textAlign: "right" }}>
                <th style={{ textAlign: "left" }}> </th><th>Customers</th><th>Churned</th><th>Avg spend</th>
              </tr>
            </thead>
            <tbody>
              {summary.by_trait[trait].map((s) => (
                <tr key={s.value} style={{ textAlign: "right", opacity: s.thin ? 0.6 : 1 }}>
                  <td style={{ textAlign: "left" }}>{s.value}</td>
                  <td>{s.customers.toLocaleString("fi-FI")} <span className="card-sub">({Math.round(s.share * 100)} %)</span></td>
                  <td>{s.churn_rate === undefined ? "–" : `${Math.round(s.churn_rate * 100)} %`}</td>
                  <td>{s.avg_spend_eur === undefined ? "–" : fmtEur(s.avg_spend_eur)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {summary.by_trait[trait].some((s) => s.thin) && <div className="card-sub" style={{ marginTop: 6 }}>Faded rows: fewer than 30 customers.</div>}
        </div>
      ))}
    </div>
  );
}
