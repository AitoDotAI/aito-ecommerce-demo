"use client";

import { useEffect } from "react";

import { fmtEur } from "@/lib/api";
import type { ActionOption, AtRiskRow, RankedActions, WinbackOffer } from "@/lib/types";

/**
 * The next best action for one at-risk customer, in a dialog: every action the shop
 * has, against doing nothing, with the chance of a visit and of an order, what it
 * costs and what it adds. Esc, the backdrop or the button closes it.
 */
export default function ActionsPopup({ customer, onClose }: { customer: AtRiskRow; onClose: () => void }) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}
         style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.35)", zIndex: 60, display: "flex",
                  alignItems: "center", justifyContent: "center", padding: 16 }}>
      <div role="dialog" aria-modal="true" aria-label={`Next best action for ${customer.name}`} className="card"
           style={{ width: "min(760px, 100%)", maxHeight: "90vh", overflowY: "auto", margin: 0 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
          <div>
            <div className="card-title" style={{ marginBottom: 2 }}>Next best action · {customer.name}</div>
            <div className="card-sub">Best: <strong>{customer.actions.best}</strong></div>
          </div>
          <button type="button" className="btn btn-ghost" style={{ fontSize: 12, padding: "2px 10px" }} onClick={onClose}>Close</button>
        </div>
        {customer.tells.length > 0 && (
          <div style={{ margin: "8px 0 2px", display: "flex", flexWrap: "wrap", gap: 6 }}>
            {customer.tells.map((tell) => <span key={tell} className="pill pill-orange">{tell}</span>)}
          </div>
        )}
        <ActionsDetail actions={customer.actions} offer={customer.offer} pets={customer.pets} />
      </div>
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
