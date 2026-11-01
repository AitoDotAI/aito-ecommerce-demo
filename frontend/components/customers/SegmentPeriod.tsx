"use client";

import { KPIS } from "@/lib/customer-kpis";
import type { PeriodComparison } from "@/lib/customer-profiles";

/**
 * The period picked on the trend, set against the rest of the history (ADR 0055): the segment's monthly averages inside the
 * period and outside it, the change, and what the same change was for everyone, so a segment's own movement shows apart from the shop's.
 */
export default function SegmentPeriod({ period, conditions, onClear }: { period: PeriodComparison; conditions: number; onClear: () => void }) {
  return (
    <div className="card" style={{ borderLeft: "4px solid var(--aito-teal)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 8 }}>
        <div className="card-title" style={{ margin: 0 }}>{period.from} … {period.to} against the other {period.months_outside} months</div>
        <button className="btn btn-ghost" style={{ padding: "2px 10px", fontSize: 12 }} onClick={onClear}>Whole history</button>
      </div>
      <div className="scroll-x">
        <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse", marginTop: 6 }}>
          <thead>
            <tr className="card-sub" style={{ textAlign: "right" }}>
              <th style={{ textAlign: "left", fontWeight: 500 }}></th><th style={{ fontWeight: 500 }}>In the period</th><th style={{ fontWeight: 500 }}>Outside</th>
              <th style={{ fontWeight: 500 }}>Change</th>{conditions > 0 && <th style={{ fontWeight: 500 }}>Everyone&apos;s change</th>}
            </tr>
          </thead>
          <tbody>
            {KPIS.map((k) => {
              const own = period.selected[k.id];
              const everyone = period.all[k.id];
              const good = own.change === null ? null : (k.higherIsBetter ? own.change >= 0 : own.change <= 0);
              return (
                <tr key={k.id} style={{ textAlign: "right", borderTop: "1px solid var(--border-light)" }}>
                  <td style={{ textAlign: "left", padding: "4px 0" }}>{k.label}</td>
                  <td>{own.inside === null ? "–" : k.format(own.inside)}</td>
                  <td>{own.outside === null ? "–" : k.format(own.outside)}</td>
                  <td style={{ fontWeight: 700, color: good === false ? "var(--cta)" : undefined }}>{own.change === null ? "–" : k.change(own.change)}</td>
                  {conditions > 0 && <td className="card-sub">{everyone.change === null ? "–" : k.change(everyone.change)}</td>}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="card-sub" style={{ marginTop: 6, lineHeight: 1.5 }}>
        Customers, purchases and revenue are monthly averages, so a short period and a long remainder compare fairly; profit per customer is weighted by
        the customers active each month. NPS and churn are read at the end of the period against the month before it. The tabs below still describe the
        whole history; the data is monthly, so a period is whole months.
      </div>
    </div>
  );
}
