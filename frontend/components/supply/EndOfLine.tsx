"use client";

import Link from "next/link";

import { fmtEur } from "@/lib/api";
import type { SupplyEndOfLine } from "@/lib/types";

/**
 * The second lever (ADR 0061): instead of adjusting supply, adjust demand. Products that tie up capital and will not clear even at the deepest
 * markdown the page tests, and have no season ahead, are candidates to end: stop reordering and sell the stock down. The page recommends, the shop decides.
 */
export default function EndOfLine({ rows, scored }: { rows: SupplyEndOfLine[]; scored: number }) {
  const capital = rows.reduce((sum, r) => sum + r.tied_capital_eur, 0);
  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div className="card-title">Candidates to end · {rows.length} of the {scored} largest, {fmtEur(capital)} tied up</div>
      <div className="card-sub" style={{ marginBottom: 8, lineHeight: 1.5 }}>
        A product that sells too slowly to clear even at the deepest markdown tested, and had no season in the months ahead a year ago, costs more to keep than it earns.
        The other lever is demand: stop reordering it, and sell the stock down with offers. Nothing is changed here; this is a list for you to decide on.
      </div>
      {rows.length === 0 && <div className="card-sub">No product among the largest fails to clear and has no season ahead.</div>}
      {rows.length > 0 && (
        <div style={{ overflowX: "auto" }}>
          <table className="recent-table" style={{ width: "100%", fontSize: 12.5 }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left" }}>Product</th>
                <th style={{ textAlign: "right" }}>Stock · excess</th>
                <th style={{ textAlign: "right" }}>Tied up</th>
                <th style={{ textAlign: "right" }}>Weeks to clear at {rows[0].discount_pct} % off</th>
                <th style={{ textAlign: "right" }}>Price at {rows[0].discount_pct} % off · cost</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.sku}>
                  <td><Link href={`/product/?sku=${r.sku}`}>{r.name}</Link><div className="card-sub">{r.sku} · {r.category}</div></td>
                  <td style={{ textAlign: "right" }}>{r.current_stock} · {r.excess_units}</td>
                  <td style={{ textAlign: "right" }}>{fmtEur(r.tied_capital_eur)}</td>
                  <td style={{ textAlign: "right" }}>{r.weeks_to_clear === null ? "never" : Math.round(r.weeks_to_clear)}</td>
                  <td style={{ textAlign: "right" }}>{fmtEur(r.price_at_deepest_eur)} · {fmtEur(r.unit_cost_eur)}{r.below_cost ? " (below cost)" : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
