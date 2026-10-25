"use client";

import { Fragment, useState } from "react";

import { fmtEur } from "@/lib/api";
import WhyPopover from "@/components/prediction/WhyPopover";
import { monthName } from "@/components/owner/DecisionCard";
import type { AtRiskRow, WinbackOffer } from "@/lib/types";

/**
 * Active customers Aito rates more likely than not to stop ordering, the
 * most spend at stake first. The risk is a word, not a percentage; the
 * `?` opens the `$why`. "Win-back offer" opens the row's action: the
 * product email with the best expected return.
 */
export default function AtRiskTable({ rows }: { rows: AtRiskRow[] }) {
  const [open, setOpen] = useState<string | null>(null);
  if (rows.length === 0) return <div className="card-sub">No active customer is likely to stop ordering.</div>;
  return (
    <div style={{ overflowX: "auto" }}>
      <table className="recent-table" style={{ width: "100%", fontSize: 12.5 }}>
        <thead>
          <tr>
            <th style={{ textAlign: "left" }}>Customer</th>
            <th style={{ textAlign: "left" }}>Last order</th>
            <th style={{ textAlign: "right" }}>Spent<br /><span style={{ fontWeight: 400 }}>last 12 months</span></th>
            <th style={{ textAlign: "left" }}>Risk</th>
            <th style={{ textAlign: "left" }}>Action</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => (
            <Fragment key={c.customer_id}>
              <tr>
                <td>
                  <strong>{c.name}</strong>
                  <div style={{ color: "var(--text-muted)", fontSize: 11 }}>
                    {c.pets.replace(/_/g, " ")}{c.pets_declared ? "" : " (from their orders)"}{c.dog_size ? ` (${c.dog_size} dog)` : ""} · {c.region} ·{" "}
                    {c.tenure_months} months a customer
                  </div>
                </td>
                <td>{monthName(c.last_order_month)}</td>
                <td style={{ textAlign: "right", fontWeight: 700 }}>{fmtEur(c.spend_12m_eur)}</td>
                <td style={{ whiteSpace: "nowrap" }}>
                  <span className={`pill ${c.risk === "very likely" ? "pill-red" : "pill-orange"}`}>{c.risk} to stop</span>
                  {c.why_explanation && (
                    <span style={{ marginLeft: 4 }}>
                      <WhyPopover why={c.why_explanation} title={`${c.name}: ${c.risk} to stop ordering`} />
                    </span>
                  )}
                </td>
                <td>
                  <button type="button" className="btn btn-ghost" style={{ fontSize: 11.5, padding: "2px 8px" }}
                          aria-expanded={open === c.customer_id}
                          onClick={() => setOpen(open === c.customer_id ? null : c.customer_id)}>
                    {open === c.customer_id ? "Hide offer" : "Win-back offer"}
                  </button>
                </td>
              </tr>
              {open === c.customer_id && (
                <tr><td colSpan={5}><OfferDetail offer={c.offer} pets={c.pets} /></td></tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function OfferDetail({ offer, pets }: { offer: WinbackOffer | null; pets: string }) {
  if (!offer) {
    return (
      <div className="card-sub" style={{ padding: "6px 4px" }}>
        No offer to suggest: no past win-back email featured a {pets.replace(/_/g, " ")} product, so there is
        no response to learn from.
      </div>
    );
  }
  return (
    <div style={{ padding: "6px 4px 10px", fontSize: 13, lineHeight: 1.6 }}>
      Email them <strong>{offer.name}</strong> ({fmtEur(offer.price_eur, 2)}). Aito estimates a{" "}
      <strong>{Math.round(offer.response_p * 100)} %</strong> chance they order after it, an order of about{" "}
      {fmtEur(offer.order_value_eur)} if they do: an expected <strong>{fmtEur(offer.expected_return_eur, 2)}</strong>{" "}
      after the email&apos;s cost.
      <div className="card-sub">
        From past win-back emails: <code>_recommend</code> picks candidates for their pets,{" "}
        <code>_predict responded</code> gives the chance, <code>_estimate order_value_eur</code> the order.
      </div>
    </div>
  );
}
