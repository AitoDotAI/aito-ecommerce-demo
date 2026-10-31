"use client";

import { useState } from "react";

import { ACTION_TITLE, FIELD_TITLE, type ProfilesSummary, type ResponseCell } from "@/lib/customer-profiles";

const ACTIONS = Object.keys(ACTION_TITLE);

function cellStyle(cell: ResponseCell) {
  if (cell.thin || cell.lift_points === null) return { background: "transparent", color: "var(--text-muted)" };
  if (!cell.clear) return { background: "var(--border-light)", color: "var(--text)" };
  return { background: cell.lift_points > 0 ? "rgba(0, 168, 150, 0.28)" : "rgba(220, 80, 60, 0.25)", color: "var(--text)" };
}

/** Who responds to what: the change in the share who ordered within 30 days, per segment and action, against no action. */
export default function ResponseMatrix({ summary }: { summary: ProfilesSummary }) {
  const [field, setField] = useState("offer_buyer");
  const rows = summary.response[field];
  return (
    <div className="card">
      <div className="card-title">Who responds to what</div>
      <div className="card-sub" style={{ marginBottom: 8 }}>
        Points more (or fewer) of the segment ordered within 30 days after the action than after none, from the shop&apos;s action
        table. Shaded: larger than its 95 % margin (the ± beside it). Grey: within the margin, so not a result. Blank: fewer than 30 rows.
      </div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 10 }}>
        {Object.entries(FIELD_TITLE).map(([key, label]) => (
          <button key={key} aria-pressed={field === key} onClick={() => setField(key)} style={{
            cursor: "pointer", borderRadius: 14, padding: "3px 12px", fontSize: 13, font: "inherit", color: "var(--text)",
            border: `1px solid ${field === key ? "var(--aito-teal)" : "var(--border)"}`,
            background: field === key ? "rgba(0, 168, 150, 0.15)" : "transparent",
          }}>{label}</button>
        ))}
      </div>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", fontSize: 13, borderCollapse: "separate", borderSpacing: 3 }}>
          <thead>
            <tr className="card-sub"><th style={{ textAlign: "left" }}>{FIELD_TITLE[field]}</th><th>No action</th>
              {ACTIONS.map((a) => <th key={a}>{ACTION_TITLE[a]}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.value} style={{ textAlign: "center" }}>
                <td style={{ textAlign: "left" }}>{row.value}</td>
                <td className="card-sub">{row.none.order_rate === null ? "–" : `${Math.round(row.none.order_rate * 100)} %`} <span>({row.none.rows})</span></td>
                {ACTIONS.map((a) => {
                  const cell = row.actions[a];
                  return (
                    <td key={a} style={{ borderRadius: 4, padding: "4px 6px", ...cellStyle(cell) }}
                      title={`${cell.rows} rows, ${cell.order_rate === null ? "–" : Math.round(cell.order_rate * 100)} % ordered`}>
                      {cell.lift_points === null ? <span>{cell.rows} rows</span>
                        : <>{cell.lift_points > 0 ? "+" : ""}{cell.lift_points}<span className="card-sub"> ±{cell.margin_points}</span></>}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
