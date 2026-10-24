"use client";

import { Fragment, useState } from "react";
import Link from "next/link";

import { fmtEur } from "@/lib/api";
import { HIGHLIGHT } from "./highlight";
import PriceBandCell from "./PriceBandCell";
import type { MarkdownProposal, SupplyOverstockRow } from "@/lib/types";

const ACTION: Record<MarkdownProposal["action"], { label: (m: MarkdownProposal) => string; pill: string }> = {
  hold:       { label: () => "Hold the price",                pill: "pill-green" },
  markdown:   { label: (m) => `Mark down ${m.discount_pct} %`, pill: "pill-orange" },
  wont_clear: { label: () => "Markdown won't clear it",        pill: "pill-red" },
};

/**
 * The largest overstock rows, each with its markdown action: hold, the
 * shallowest discount that clears the excess within a quarter, or "won't
 * clear" when even the deepest doesn't. "Details" opens Aito's estimate at
 * every level, so the choice can be checked.
 */
export default function OverstockTable({ rows, highlight }: { rows: SupplyOverstockRow[]; highlight?: string }) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <div style={{ overflowX: "auto" }}>
      <table className="recent-table" style={{ width: "100%", fontSize: 12.5 }}>
        <thead>
          <tr>
            <th style={{ textAlign: "left" }}>Product</th>
            <th style={{ textAlign: "right" }}>Stock · excess</th>
            <th style={{ textAlign: "right" }}>Tied up</th>
            <th style={{ textAlign: "right" }}>Price</th>
            <th style={{ textAlign: "left" }}>Markdown</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <Fragment key={r.sku}>
              <tr id={`row-${r.sku}`} style={highlight === r.sku ? HIGHLIGHT : undefined}>
                <td>
                  <Link href={`/product/?sku=${encodeURIComponent(r.sku)}`} style={{ fontWeight: 700 }}>
                    {r.name}
                  </Link>
                  <div style={{ color: "var(--text-muted)", fontSize: 11 }}>{r.category.replace(/-/g, " ")}</div>
                </td>
                <td style={{ textAlign: "right" }}>
                  <strong>{r.current_stock}</strong> · {r.excess_units}
                  <div style={{ fontSize: 11, color: "var(--text-muted)" }}>reorder at {r.reorder_point}</div>
                </td>
                <td style={{ textAlign: "right", fontWeight: 700 }}>{fmtEur(r.tied_capital_eur)}</td>
                <td style={{ textAlign: "right" }}><PriceBandCell price={r.price} /></td>
                <td>
                  <MarkdownCell m={r.markdown} />
                  <button type="button" className="btn btn-ghost" onClick={() => setOpen(open === r.sku ? null : r.sku)}
                          aria-expanded={open === r.sku} style={{ fontSize: 11, padding: "0 6px", marginTop: 4 }}>
                    {open === r.sku ? "Hide" : "Details"}
                  </button>
                </td>
              </tr>
              {open === r.sku && (
                <tr><td colSpan={5}><MarkdownCurve row={r} /></td></tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MarkdownCell({ m }: { m: MarkdownProposal }) {
  const action = ACTION[m.action];
  const weeks = m.weeks_to_clear === null ? "never" : `${m.weeks_to_clear} weeks`;
  return (
    <div>
      <span className={`pill ${action.pill}`} style={{ fontWeight: 700 }}>{action.label(m)}</span>
      <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 3 }}>
        {m.action === "hold" && <>clears in {weeks} at full price</>}
        {m.action === "markdown" && (
          <>clears in {weeks}: +{m.extra_units_vs_full_price} units, {fmtEur(m.capital_freed_eur)} freed,
            {" "}{fmtEur(m.margin_given_up_eur)} margin given up</>
        )}
        {m.action === "wont_clear" && <>even at {m.discount_pct} % off: {weeks} to clear</>}
      </div>
    </div>
  );
}

function MarkdownCurve({ row }: { row: SupplyOverstockRow }) {
  return (
    <div style={{ padding: "6px 4px 10px" }}>
      <div className="card-sub" style={{ marginBottom: 6 }}>
        Aito&apos;s estimate of next month&apos;s units at each price (<code>_estimate units_sold</code>,
        {" "}<code>model: &quot;regression&quot;</code>), and the weeks the {row.excess_units} excess units take to sell.
      </div>
      <table className="recent-table" style={{ fontSize: 12 }}>
        <thead>
          <tr><th>Discount</th><th style={{ textAlign: "right" }}>Price</th>
            <th style={{ textAlign: "right" }}>Units / month</th><th style={{ textAlign: "right" }}>Weeks to clear</th></tr>
        </thead>
        <tbody>
          {row.markdown.curve.map((p) => (
            <tr key={p.discount_pct} style={p.discount_pct === row.markdown.discount_pct ? { fontWeight: 700 } : undefined}>
              <td>{p.discount_pct} %</td>
              <td style={{ textAlign: "right" }}>{fmtEur(p.price_eur, 2)}</td>
              <td style={{ textAlign: "right" }}>{p.monthly_units.toFixed(1)}</td>
              <td style={{ textAlign: "right" }}>{p.weeks_to_clear ?? "never"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
