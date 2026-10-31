"use client";

import { fmtEur } from "@/lib/api";
import { ACTION_TITLE, type ProfilesSummary, type ResponseCell } from "@/lib/customer-profiles";

function shade(cell: ResponseCell, clear: boolean | null, lift: number | null) {
  if (cell.thin || lift === null) return { color: "var(--text-muted)" };
  if (!clear) return { background: "var(--border-light)" };
  return { background: lift > 0 ? "rgba(0, 168, 150, 0.28)" : "rgba(220, 80, 60, 0.25)" };
}

/** What the shop's actions did for the selected segment, in orders and in estimated profit, against no action. */
export default function SegmentResponse({ summary, selected }: { summary: ProfilesSummary; selected: string }) {
  const entry = summary.response[selected];
  if (!entry) return null;
  return (
    <div className="card">
      <div className="card-title">What the shop&apos;s actions did for them</div>
      <div className="card-sub" style={{ marginBottom: 8, lineHeight: 1.5 }}>
        Observed in the shop&apos;s action table (simulated), against no action in this segment ({entry.none.rows} rows
        {entry.none.order_rate === null ? "" : `, ${Math.round(entry.none.order_rate * 100)} % ordered`}
        {entry.none.profit_eur === null ? "" : `, ${fmtEur(entry.none.profit_eur, 2)} profit per row`}).
        Orders: points more or fewer who ordered within 30 days. Profit: the 30-day spend at the shop&apos;s {Math.round(summary.gross_margin * 100)} % gross
        margin less the action&apos;s cost, per row. Shaded: larger than its 95 % margin; the margins are approximate, because one customer
        can have several rows, and about one cell in twenty passes by chance. A difference does not prove the action caused the order.
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
