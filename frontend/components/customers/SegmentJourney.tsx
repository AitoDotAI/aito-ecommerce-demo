"use client";

import { useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";

interface Cell { offset: number; churned: number | null; active: number | null; n_churned: number; n_active: number; points: number | null; margin: number | null; clear: boolean | null }
interface Journey {
  too_small: boolean; customers: { churned: number; active: number }; comparable?: boolean; reason?: string;
  offsets?: number[]; events?: { code: string; label: string }[]; cells?: Record<string, Cell[]>;
}

const pct = (n: number | null) => (n === null ? "–" : `${Math.round(n * 100)} %`);
const label = (offset: number) => (offset === 0 ? "Last order" : offset < 0 ? `${-offset} before` : `${offset} after`);

/**
 * The journey of the segment (ADR 0059): every customer is lined up on their own last order, and each cell is the share of those who left (top) and of those who stayed
 * (below) with that kind of event in the month. A shaded cell is a difference beyond chance. The data is monthly: the order of events within a month is not known.
 */
export default function SegmentJourney({ conditions }: { conditions: string[] }) {
  const [journey, setJourney] = useState<Journey | null>(null);
  const [error, setError] = useState<string | null>(null);
  const query = conditions.map((c) => `c=${encodeURIComponent(c)}`).join("&");

  useEffect(() => {
    apiFetch<Journey>(`/api/customer-profiles/journey${query ? `?${query}` : ""}`).then((j) => { setJourney(j); setError(null); }).catch((e) => setError(String(e)));
  }, [query]);

  if (error) return <div className="card card-sub">{error}</div>;
  if (!journey) return <div className="card" style={{ height: 160, background: "var(--border-light)" }} />;
  if (journey.too_small || !journey.cells || !journey.offsets || !journey.events) return <div className="card card-sub">Too few customers in this segment to compare.</div>;
  return (
    <div className="card">
      <div className="card-title">The months around the last order: those who left against those who stayed</div>
      <div className="card-sub" style={{ lineHeight: 1.5, marginBottom: 8 }}>
        {journey.customers.churned.toLocaleString("en-GB")} customers who left (no order in the last three months of the data) and {journey.customers.active.toLocaleString("en-GB")} who stayed,
        each lined up on their own last order. Each cell: the share with the event that month, those who left on top and those who stayed below. {journey.comparable ? "Shaded: the difference is beyond chance (99.7 %)." : `Not compared: ${journey.reason}.`}
      </div>
      <div className="scroll-x">
        <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
          <thead>
            <tr className="card-sub">
              <th style={{ textAlign: "left", fontWeight: 500 }}>Month</th>
              {journey.offsets.map((o) => <th key={o} style={{ fontWeight: o === 0 ? 700 : 500, padding: "2px 6px", whiteSpace: "nowrap" }}>{label(o)}</th>)}
            </tr>
          </thead>
          <tbody>
            {journey.events.map((e) => (
              <tr key={e.code} style={{ borderTop: "1px solid var(--border-light)", textAlign: "center" }}>
                <td style={{ textAlign: "left", padding: "4px 8px 4px 0" }}>{e.label}</td>
                {journey.cells![e.code].map((cell) => (
                  <td key={cell.offset} title={cell.points === null ? "Not compared" : `${cell.points > 0 ? "+" : ""}${cell.points} points; margin ±${cell.margin}; ${cell.n_churned} left, ${cell.n_active} stayed`}
                      style={{ padding: "3px 6px", background: cell.clear ? "rgba(0, 168, 150, 0.2)" : undefined, lineHeight: 1.25 }}>
                    <div style={{ fontWeight: 600 }}>{pct(cell.churned)}</div>
                    <div className="card-sub" style={{ fontSize: 12 }}>{pct(cell.active)}</div>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
