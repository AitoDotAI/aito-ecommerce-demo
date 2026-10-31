"use client";

import { useState } from "react";
import Link from "next/link";

import Confidence from "@/components/customers/Confidence";
import { fmtEur } from "@/lib/api";
import { ACQUISITION_TITLE, type AcquisitionRow, type SegmentView } from "@/lib/customer-profiles";

const DIMENSIONS = ["source", "landing", "landing_category"] as const;

/** Where the segment's customers came from: channel, landing page, landing category, and what they earned. */
export default function SegmentAcquisition({ view }: { view: SegmentView }) {
  const [dimension, setDimension] = useState<(typeof DIMENSIONS)[number]>("source");
  const entry = view.acquisition;
  if (!entry || !entry[dimension]) return null;
  const rows = entry[dimension];
  const everyone = view.conditions.length === 0;
  return (
    <div className="card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 8 }}>
        <div className="card-title" style={{ margin: 0 }}>Where they come from</div>
        <span style={{ display: "inline-flex", gap: 4 }}>
          {DIMENSIONS.map((d) => (
            <button key={d} aria-pressed={dimension === d} onClick={() => setDimension(d)} style={{
              cursor: "pointer", borderRadius: 12, padding: "2px 10px", font: "inherit", fontSize: 12, color: "var(--text)",
              border: `1px solid ${dimension === d ? "var(--aito-teal)" : "var(--border)"}`,
              background: dimension === d ? "rgba(0, 168, 150, 0.15)" : "transparent" }}>{ACQUISITION_TITLE[d]}</button>
          ))}
        </span>
      </div>
      <div className="card-sub" style={{ margin: "6px 0 8px", lineHeight: 1.5 }}>
        The first session of each customer, found through their visitor id: only what was known when they arrived.
        {everyone ? " Profit per customer by how they came, for all profiled customers." : " Points: how many more (or fewer) of this segment came that way than of the other customers; confidence is the difference divided by its 99.7 % margin."}{" "}
        Profit per customer is shown where 30 or more customers stand behind it.{" "}
        <Link href="/acquisition/">The Acquisition view →</Link>
      </div>
      <div className="scroll-x">
      <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
        <thead>
          <tr className="card-sub" style={{ textAlign: "right" }}>
            <th style={{ textAlign: "left" }}> </th><th>Customers</th>
            {!everyone && <th style={{ textAlign: "left", paddingLeft: 12 }}>Segment vs others</th>}
            {!everyone && <th>Confidence</th>}<th>Profit per customer</th>{!everyone && <th>All from here</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => <Row key={r.value} r={r} everyone={everyone} />)}
        </tbody>
      </table>
      </div>
    </div>
  );
}

function Row({ r, everyone }: { r: AcquisitionRow; everyone: boolean }) {
  const label = r.value.replace("_", " ");
  return (
    <tr style={{ textAlign: "right" }}>
      <td style={{ textAlign: "left", padding: "3px 4px" }}>{label}</td>
      <td style={{ paddingLeft: 8 }}>{r.customers} <span className="card-sub">({Math.round(r.share * 100)} %)</span></td>
      {!everyone && (
        <td style={{ textAlign: "left", paddingLeft: 12, whiteSpace: "nowrap" }}>
          {r.points !== undefined && <>{r.points > 0 ? "+" : ""}{r.points} <span className="card-sub">±{r.margin_points} ({Math.round(r.share * 100)} % vs {Math.round((r.share_others ?? 0) * 100)} %)</span></>}
        </td>
      )}
      {!everyone && <td style={{ paddingLeft: 8 }}>{r.points !== undefined && <Confidence points={r.points} margin={r.margin_points ?? 0} />}</td>}
      <td style={{ paddingLeft: 8 }}>
        {r.profit_per_customer_eur === null ? <span className="card-sub">n={r.customers}</span> : <strong>{fmtEur(r.profit_per_customer_eur)}</strong>}
        {r.profit_per_customer_ci && <span className="card-sub"> ±{Math.round((r.profit_per_customer_ci[1] - r.profit_per_customer_ci[0]) / 2)}</span>}
      </td>
      {!everyone && <td style={{ paddingLeft: 8 }}>{r.profit_per_customer_all_eur === null ? "–" : fmtEur(r.profit_per_customer_all_eur)}</td>}
    </tr>
  );
}
