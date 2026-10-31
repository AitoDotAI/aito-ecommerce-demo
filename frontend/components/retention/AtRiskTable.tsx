"use client";

import { useState } from "react";

import { fmtEur } from "@/lib/api";
import WhyPopover from "@/components/prediction/WhyPopover";
import { monthName } from "@/components/owner/DecisionCard";
import type { AtRiskRow } from "@/lib/types";
import ActionsPopup from "./ActionsPopup";

/**
 * Active customers Aito rates more likely than not to stop ordering, the
 * most spend at stake first. The risk is a word, not a percentage; the
 * `?` opens the `$why`. The tells under a name are what the shop observed
 * (a detractor answer, a poor review, a return, a late delivery). The action
 * column names the best of the shop's actions for that customer and opens
 * all of them in a dialog, each against doing nothing.
 */
export default function AtRiskTable({ rows }: { rows: AtRiskRow[] }) {
  const [open, setOpen] = useState<AtRiskRow | null>(null);
  if (rows.length === 0) return <div className="card-sub">No active customer is likely to stop ordering.</div>;
  return (
    <div style={{ overflowX: "auto" }}>
      <table className="recent-table" style={{ width: "100%", fontSize: 12.5 }}>
        <thead>
          <tr>
            <th style={{ textAlign: "left" }}>Customer</th>
            <th style={{ textAlign: "left" }}>Last order</th>
            <th style={{ textAlign: "right" }}>Spent<br /><span style={{ fontWeight: 400 }}>last 12 months</span></th>
            <th style={{ textAlign: "left", paddingLeft: 28 }}>Risk</th>
            <th style={{ textAlign: "left" }}>Next best action</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => (
            <tr key={c.customer_id}>
              <td>
                <strong>{c.name}</strong>
                <div style={{ color: "var(--text-muted)", fontSize: 11 }}>
                  {c.pets.replace(/_/g, " ")}{c.pets_declared ? "" : " (from their orders)"}{c.dog_size ? ` (${c.dog_size} dog)` : ""} · {c.region} ·{" "}
                  {c.tenure_months} {c.tenure_months === 1 ? "month" : "months"} a customer
                </div>
                {c.tells.length > 0 && (
                  <div style={{ marginTop: 3, display: "flex", flexWrap: "wrap", gap: 4 }}>
                    {c.tells.map((tell) => <span key={tell} className="pill pill-orange" style={{ fontSize: 10.5 }}>{tell}</span>)}
                  </div>
                )}
              </td>
              <td>{monthName(c.last_order_month)}</td>
              <td style={{ textAlign: "right", fontWeight: 700 }}>{fmtEur(c.spend_12m_eur)}</td>
              <td style={{ whiteSpace: "nowrap", paddingLeft: 28 }}>
                <span className={`pill ${c.risk === "very likely" ? "pill-red" : "pill-orange"}`}>{c.risk} to stop</span>
                {c.why_explanation && (
                  <span style={{ marginLeft: 4 }}>
                    <WhyPopover why={c.why_explanation} title={`${c.name}: ${c.risk} to stop ordering`} />
                  </span>
                )}
              </td>
              <td>
                <button type="button" className="btn btn-ghost" style={{ fontSize: 11.5, padding: "2px 8px" }}
                        aria-haspopup="dialog" onClick={() => setOpen(c)}>
                  {c.actions.best}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {open && <ActionsPopup customer={open} onClose={() => setOpen(null)} />}
    </div>
  );
}
