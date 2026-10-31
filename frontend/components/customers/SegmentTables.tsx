"use client";

import { fmtEur } from "@/lib/api";
import { TRAIT_TITLE, type ProfilesSummary } from "@/lib/customer-profiles";

/** How customers shop, by trait: size, churn and spend of each group. Counts of what they bought, not guesses about them. */
export default function SegmentTables({ summary }: { summary: ProfilesSummary }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(440px, 1fr))", gap: 12 }}>
      {(Object.keys(TRAIT_TITLE) as (keyof typeof summary.by_trait)[]).map((trait) => (
        <div key={trait} className="card">
          <div className="card-title">{TRAIT_TITLE[trait]}</div>
          <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
            <thead>
              <tr className="card-sub" style={{ textAlign: "right" }}>
                <th style={{ textAlign: "left" }}> </th><th>Customers</th><th>Revenue</th><th>12 months</th><th>Churned</th>
              </tr>
            </thead>
            <tbody>
              {summary.by_trait[trait].map((s) => (
                <tr key={s.value} style={{ textAlign: "right", whiteSpace: "nowrap", opacity: s.thin ? 0.6 : 1 }}>
                  <td style={{ textAlign: "left" }}>{s.value}</td>
                  <td>{s.customers.toLocaleString("fi-FI")} <span className="card-sub">({Math.round(s.share * 100)} %)</span></td>
                  <td title={s.avg_spend_eur === undefined ? undefined : `${fmtEur(s.avg_spend_eur)} per customer`}>
                    {s.revenue_eur === undefined ? "–" : fmtEur(s.revenue_eur)}{" "}
                    <span className="card-sub">({Math.round((s.revenue_share ?? 0) * 100)} %)</span>
                  </td>
                  <td>{s.revenue_12m_eur === undefined ? "–" : fmtEur(s.revenue_12m_eur)}</td>
                  <td>{s.churn_rate === undefined ? "–" : `${Math.round(s.churn_rate * 100)} %`}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="card-sub" style={{ marginTop: 6 }}>
            Faded rows: fewer than 30 customers. Revenue is the sum of the customers&apos; orders; the share is of all profiled
            customers&apos; revenue (pets and diets overlap, so their shares add up to more than 100 %). Hover for revenue per customer.
          </div>
        </div>
      ))}
    </div>
  );
}
