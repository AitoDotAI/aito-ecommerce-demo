"use client";

import { useState } from "react";
import Link from "next/link";

import { fmtEur } from "@/lib/api";
import { HIGHLIGHT } from "./highlight";
import PriceBandCell from "./PriceBandCell";
import type { SupplyReorderRow } from "@/lib/types";

/**
 * The reorder queue: every SKU below its reorder point, the most revenue
 * at risk first. The order covers what the product sold a month over the
 * last three months, plus safety stock: observed sales, not a forecast.
 */
const FIRST_SHOWN = 15;

export default function ReorderTable({ rows, month, highlight }: {
  rows: SupplyReorderRow[]; month: string; highlight?: string;
}) {
  // A linked row counts as asked for: show them all so it can be highlighted.
  const [all, setAll] = useState(false);
  const shown = all || (highlight && rows.findIndex((r) => r.sku === highlight) >= FIRST_SHOWN)
    ? rows : rows.slice(0, FIRST_SHOWN);
  if (rows.length === 0) {
    return <div className="card-sub">No SKU is below its reorder point.</div>;
  }
  return (
    <div style={{ overflowX: "auto" }}>
      <table className="recent-table" style={{ width: "100%", fontSize: 12.5 }}>
        <thead>
          <tr>
            <th style={{ textAlign: "left" }}>Product · supplier</th>
            <th style={{ textAlign: "right" }}>Stock</th>
            <th style={{ textAlign: "right" }} title={`Units a month over the last three months, up to the month before ${month}`}>Sold a month<br /><span style={{ fontWeight: 400 }}>last 3 months</span></th>
            <th style={{ textAlign: "right" }}>Order</th>
            <th style={{ textAlign: "right" }}>Revenue<br /><span style={{ fontWeight: 400 }}>at risk</span></th>
            <th style={{ textAlign: "right" }}>Price</th>
          </tr>
        </thead>
        <tbody>
          {shown.map((r) => (
            <tr key={r.sku} id={`row-${r.sku}`} style={highlight === r.sku ? HIGHLIGHT : undefined}>
              <td>
                <Link href={`/product/?sku=${encodeURIComponent(r.sku)}`} style={{ fontWeight: 700 }}>
                  {r.name}
                </Link>
                <div style={{ color: "var(--text-muted)", fontSize: 11 }}>
                  {r.sku} · {r.supplier} · {r.lead_time_days} d lead time
                </div>
              </td>
              <td style={{ textAlign: "right" }}>
                <strong>{r.current_stock}</strong>
                <div style={{ fontSize: 11, color: "var(--text-muted)" }}>reorder at {r.reorder_point}</div>
              </td>
              <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                {r.recent_units === 0 ? (
                  <span className="card-sub" title="Nothing sold in the last three months">none</span>
                ) : (
                  <strong>{r.recent_units}</strong>
                )}
              </td>
              <td style={{ textAlign: "right" }}>
                <span className="pill pill-orange" style={{ fontWeight: 700 }}>{r.order_qty}</span>
                <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{fmtEur(r.order_cost_eur)}</div>
              </td>
              <td style={{ textAlign: "right", fontWeight: 700, color: r.revenue_at_risk_eur > 0 ? "var(--red)" : undefined }}>
                {fmtEur(r.revenue_at_risk_eur)}
              </td>
              <td style={{ textAlign: "right" }}><PriceBandCell price={r.price} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      {shown.length < rows.length && (
        <button type="button" className="btn btn-ghost" style={{ marginTop: 8 }} onClick={() => setAll(true)}>
          Show all {rows.length}
        </button>
      )}
    </div>
  );
}
