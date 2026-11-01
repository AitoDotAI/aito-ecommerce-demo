"use client";

import { KPIS } from "@/lib/customer-kpis";
import type { PeriodComparison } from "@/lib/customer-profiles";

/**
 * The period picked on the trend, set against the period just before it and as long (ADR 0055): a week against the week before, three
 * months against the three before. Both are one statistical context, the customers who ordered in either; each figure shows the change,
 * and whether it is beyond the margin of what the same customers would show by chance. Beside it, what the same change was for everyone.
 */
export default function SegmentPeriod({ period, conditions, onClear }: { period: PeriodComparison; conditions: number; onClear: () => void }) {
  const { previous, figures, all } = period;
  return (
    <div className="card" style={{ borderLeft: "4px solid var(--aito-teal)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 8 }}>
        <div className="card-title" style={{ margin: 0 }}>
          {period.from} … {period.to}{previous ? <> against {previous.from} … {previous.to}</> : null}
        </div>
        <button className="btn btn-ghost" style={{ padding: "2px 10px", fontSize: 12 }} onClick={onClear}>Whole history</button>
      </div>
      {!previous || !figures ? (
        <div className="card-sub" style={{ marginTop: 6 }}>{period.reason}. Pick a later or a shorter period.</div>
      ) : (
        <>
          <div className="scroll-x">
            <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse", marginTop: 6 }}>
              <thead>
                <tr className="card-sub" style={{ textAlign: "right" }}>
                  <th style={{ textAlign: "left", fontWeight: 500 }}></th><th style={{ fontWeight: 500 }}>This period</th><th style={{ fontWeight: 500 }}>Previous</th>
                  <th style={{ fontWeight: 500 }}>Change</th>{conditions > 0 && <th style={{ fontWeight: 500 }}>Everyone&apos;s change</th>}
                </tr>
              </thead>
              <tbody>
                {KPIS.map((k) => {
                  const own = figures[k.id];
                  const everyone = all?.[k.id];
                  const worse = own.change === null ? false : (k.higherIsBetter ? own.change < 0 : own.change > 0);
                  const show = (n: number | null) => (n === null ? "–" : k.format(n));
                  return (
                    <tr key={k.id} style={{ textAlign: "right", borderTop: "1px solid var(--border-light)" }}>
                      <td style={{ textAlign: "left", padding: "4px 0" }}>{k.label}</td>
                      <td>{show(own.this)}</td>
                      <td>{show(own.previous)}</td>
                      <td style={{ fontWeight: own.clear ? 700 : 400, color: own.clear && worse ? "var(--cta)" : undefined }}
                          title={own.margin === null ? "No margin: a count of customers" : `A change beyond ±${k.change(own.margin).replace(/^[+−]/, "")} is not chance`}>
                        {own.change === null ? "–" : k.change(own.change)}{own.clear === false ? " ·" : ""}
                      </td>
                      {conditions > 0 && <td className="card-sub">{everyone?.change == null ? "–" : k.change(everyone.change)}</td>}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="card-sub" style={{ marginTop: 6, lineHeight: 1.5 }}>
            The {period.context_customers?.toLocaleString("en-GB")}{" "}customers who ordered in either period, each against themselves: orders, revenue and profit are per
            customer. NPS is of the answers given in each period; churn is the share of customers who had ordered by then that had not in the three months up to the
            period&apos;s end. Bold: the change is beyond what chance gives at 95 % (churn 99.7 %); a dot after it: it is not. The tabs below still describe the whole
            history; the data is monthly, so a period is whole months.
          </div>
        </>
      )}
    </div>
  );
}
