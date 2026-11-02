"use client";

import { useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";

interface PatternRow { label: string; k: number; overall: number; p: number; lift: number | null; aito: { lift: number } | null; products: number | null }
interface Group { title: string; rows: number; of: number; sections: Record<string, PatternRow[]> }

const SHOWN = 10;
export const PATTERN_SECTIONS = [["mined by Aito ($patterns)", "Rules"], ["words mined by Aito ($patterns)", "Words"], ["products", "Products"], ["brand and product-name word", "Product lines"]] as const;
const SECTION_TITLE: Record<string, string> = Object.fromEntries(PATTERN_SECTIONS);
const pill = (on: boolean) => ({ cursor: "pointer", borderRadius: 12, padding: "2px 10px", font: "inherit", fontSize: 12, color: "var(--text)",
  border: `1px solid ${on ? "var(--aito-teal)" : "var(--border)"}`, background: on ? "rgba(0, 168, 150, 0.15)" : "transparent" });
const chance = (p: number) => (p < 1e-4 ? "< 0.0001" : p.toFixed(4));

/**
 * What stands out among poor reviews and detractors: products, product lines and AND-rules that are over-represented, with the rows behind each and whether
 * it is clear (the chance of luck, times the number of candidates tried, is under 5 %). Prototype: it covers all customers, not the selected segment.
 */
export default function SegmentFeedbackPatterns({ section }: { section: string }) {
  const [data, setData] = useState<Record<string, Group> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [groupKey, setGroupKey] = useState("stars");
  useEffect(() => { apiFetch<Record<string, Group>>("/api/feedback-patterns").then(setData).catch((e) => setError(String(e))); }, []);
  if (error) return <div className="card-sub">{error}</div>;
  if (!data) return <div style={{ height: 160, background: "var(--border-light)", borderRadius: 6 }} />;
  const group = data[groupKey];
  const rows = group.sections[section] ?? [];
  const tests = rows.length;
  const shown = [...rows].sort((a, b) => a.p - b.p).slice(0, SHOWN);
  return (
    <div>
      <div style={{ display: "inline-flex", gap: 4, margin: "0 0 4px", flexWrap: "wrap" }}>
        {Object.entries(data).map(([key, g]) => <button key={key} aria-pressed={groupKey === key} onClick={() => setGroupKey(key)} style={pill(groupKey === key)}>{g.title}</button>)}
      </div>
      <div className="card-sub" style={{ lineHeight: 1.5, marginBottom: 6 }}>
        Among {group.rows.toLocaleString("en-GB")} of {group.of.toLocaleString("en-GB")} rows, which {SECTION_TITLE[section].toLowerCase()} come up more than luck explains.
        {" "}{tests} tried, {rows.filter((r) => r.p * tests < 0.05).length} clear. <strong>Clear?</strong> is Yes when the chance of luck, counted over everything tried in this list, is under 5 %.
        Covers all customers, not the selected segment.
      </div>
      <div className="scroll-x">
        <table style={{ width: "100%", fontSize: 12.5, borderCollapse: "collapse" }}>
          <thead>
            <tr className="card-sub" style={{ fontSize: 11.5, textAlign: "left" }}>
              <th>Pattern</th><th>In group</th><th title="How many times likelier than in all rows">Lift</th><th title="How often luck alone would give this many">Chance</th><th>Clear?</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.label} style={{ borderTop: "1px solid var(--border-light)" }}>
                <td style={{ padding: "3px 6px 3px 0", overflowWrap: "anywhere" }}>{r.label.replace(/product_state\.|product_sku\./g, "").replace(/\s+\[→.*\]$/, "")}</td>
                <td style={{ paddingRight: 8, whiteSpace: "nowrap" }}>{r.k} of {r.overall}</td>
                <td style={{ paddingRight: 8 }}>{r.lift === null ? "–" : r.lift.toFixed(1)}</td>
                <td style={{ paddingRight: 8, whiteSpace: "nowrap" }}>{chance(r.p)}</td>
                <td style={{ fontWeight: r.p * tests < 0.05 ? 700 : 400 }}>{r.p * tests < 0.05 ? "Yes" : "–"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="card-sub" style={{ marginTop: 8 }}><a href="/feedback-patterns/">All candidates, with Aito&apos;s own numbers</a></div>
    </div>
  );
}
