"use client";

import { Fragment, useState } from "react";

import { fmtEur } from "@/lib/api";
import WhyPopover from "@/components/prediction/WhyPopover";
import { monthName } from "@/components/owner/DecisionCard";
import type { ActionOption, AtRiskRow, RankedActions, WinbackOffer } from "@/lib/types";

/**
 * Active customers Aito rates more likely than not to stop ordering, the
 * most spend at stake first. The risk is a word, not a percentage; the
 * `?` opens the `$why`. The action column names the best of the shop's
 * actions for that customer and opens all of them, each against doing nothing.
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
            <th style={{ textAlign: "left", paddingLeft: 28 }}>Risk</th>
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
                          aria-expanded={open === c.customer_id}
                          onClick={() => setOpen(open === c.customer_id ? null : c.customer_id)}>
                    {open === c.customer_id ? "Hide actions" : c.actions.best}
                  </button>
                </td>
              </tr>
              {open === c.customer_id && (
                <tr><td colSpan={5}><ActionsDetail actions={c.actions} offer={c.offer} pets={c.pets} /></td></tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const CONTEXT_WORDS: Record<string, (v: string) => string> = {
  recency_bucket: (v) => `last order ${v === "180d+" ? "over 180 days ago" : v === "0-90d" ? "within 90 days" : "90–180 days ago"}`,
  offer_buyer: (v) => `buys on offer: ${v}`,
  open_issue: (v) => (v === "none" ? "no open issue" : v.replace("_", " ")),
  email_history: (v) => (v === "never_sent" ? "no earlier win-back email" : `earlier emails: ${v}`),
  tracking_consent: (v) => (v === "yes" ? "consented to tracking" : "declined tracking"),
  spend_band: (v) => `${v} spender`,
};

function ActionsDetail({ actions, offer, pets }: { actions: RankedActions; offer: WinbackOffer | null; pets: string }) {
  return (
    <div style={{ padding: "6px 4px 10px", fontSize: 13, lineHeight: 1.6 }}>
      <div className="card-sub" style={{ marginBottom: 6 }}>
        As the shop reads them: {Object.entries(actions.context).map(([k, v]) => CONTEXT_WORDS[k]?.(v) ?? v).join(" · ")}.
        An order is worth about {fmtEur(actions.order_value_eur)}.
      </div>
      <table className="recent-table" style={{ width: "100%", fontSize: 12.5 }}>
        <thead>
          <tr>
            <th style={{ textAlign: "left" }}>Action</th>
            <th style={{ textAlign: "right" }}>Visits</th>
            <th style={{ textAlign: "right" }}>Orders</th>
            <th style={{ textAlign: "right" }}>Cost</th>
            <th style={{ textAlign: "right" }}>Adds over no action</th>
          </tr>
        </thead>
        <tbody>
          {actions.options.map((o: ActionOption, i) => (
            <tr key={o.label} style={i === 0 ? { fontWeight: 700 } : undefined}>
              <td>{o.label}</td>
              <td style={{ textAlign: "right" }}>{Math.round(o.visit_p * 100)} %</td>
              <td style={{ textAlign: "right" }}>
                {Math.round(o.purchase_p * 100)} %
                {o.action !== "none" && <span style={{ color: "var(--text-muted)", fontWeight: 400 }}> ({o.purchase_lift_p >= 0 ? "+" : "−"}{Math.abs(Math.round(o.purchase_lift_p * 100))})</span>}
              </td>
              <td style={{ textAlign: "right" }}>{fmtEur(o.cost_eur, 2)}</td>
              <td style={{ textAlign: "right", color: o.net_vs_none_eur < 0 ? "var(--red, #c0392b)" : undefined }}>
                {o.action === "none" ? "baseline" : fmtEur(o.net_vs_none_eur, 2)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="card-sub" style={{ marginTop: 6 }}>
        From the shop&apos;s past actions, simulated: <code>_predict purchased_30d</code> and <code>visited_30d</code> with this
        context and each action, <code>_estimate spend_30d_eur</code> for the order. A discount or voucher is paid on every
        order, including those that would have come anyway.
      </div>
      <OfferDetail offer={offer} pets={pets} />
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
      If it is the email: send <strong>{offer.name}</strong> ({fmtEur(offer.price_eur, 2)}). Aito estimates a{" "}
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
