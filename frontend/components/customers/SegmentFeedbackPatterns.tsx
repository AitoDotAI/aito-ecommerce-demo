"use client";

import { useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";

export interface FeedbackFilter { tab: "reviews" | "nps"; label: string; everyone: boolean; spec: { group: string; clauses: Record<string, string>[] } }
interface PatternRow { clauses: Record<string, string>[]; label: string; k: number; overall: number; p: number; lift: number | null; aito: { lift: number } | null; products: number | null }
interface Group { title: string; rows: number; of: number; sections: Record<string, PatternRow[]> }
type Lists = Record<string, Group> & { too_small?: boolean; customers?: number; min_customers?: number }

const SHOWN = 10;
export const PATTERN_SECTIONS = [["mined by Aito ($patterns)", "Patterns"], ["themes", "Themes"], ["products and themes", "Products × themes"], ["products", "Products"], ["brand and product-name word", "Product lines"]] as const;
const SECTION_TITLE: Record<string, string> = Object.fromEntries(PATTERN_SECTIONS);
const pill = (on: boolean) => ({ cursor: "pointer", borderRadius: 12, padding: "2px 10px", font: "inherit", fontSize: 12, color: "var(--text)",
  border: `1px solid ${on ? "var(--aito-teal)" : "var(--border)"}`, background: on ? "rgba(0, 168, 150, 0.15)" : "transparent" });
const chance = (p: number) => (p < 1e-4 ? "< 0.0001" : p.toFixed(4));

/**
 * What stands out among poor reviews and detractors: products, product lines and AND-rules that are over-represented, with the rows behind each and whether
 * it is clear (the chance of luck, times the number of candidates tried, is under 5 %). Prototype: with a segment ticked the lists are counted over that
 * segment's reviews and answers, except the AND-rules Aito mines, which are stored for all customers only.
 */
export default function SegmentFeedbackPatterns({ section, conditions, selected, onSelect }: { section: string; conditions: string[]; selected: FeedbackFilter | null; onSelect: (filter: FeedbackFilter | null) => void }) {
  const [data, setData] = useState<Lists | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [groupKey, setGroupKey] = useState("stars");
  const everyone = conditions.length === 0 || section === PATTERN_SECTIONS[0][0];
  const key = JSON.stringify([everyone, everyone ? [] : conditions]);
  useEffect(() => {
    let current = true;
    setData(null);
    const path = everyone ? "/api/feedback-patterns" : `/api/customer-profiles/feedback-patterns?${conditions.map((c) => `c=${encodeURIComponent(c)}`).join("&")}`;
    apiFetch<Lists>(path).then((d) => { if (current) { setData(d); setError(null); } }).catch((e) => { if (current) setError(String(e)); });
    return () => { current = false; };
    // `key` stands for the conditions and where the lists come from, which the request reads.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  if (error) return <div className="card-sub">{error}</div>;
  if (!data) return <div style={{ height: 160, background: "var(--border-light)", borderRadius: 6 }} />;
  if (data.too_small) return <div className="card-sub">Only {data.customers} customers meet these conditions; a list needs {data.min_customers} before it says anything.</div>;
  const group = data[groupKey] as Group;
  const rows = group.sections[section] ?? [];
  const tests = rows.length;
  const labelOf = (r: PatternRow) => r.label.replace(/product_state\.|product_sku\./g, "").replace(/\s+\[→.*\]$/, "");
  const filterOf = (r: PatternRow): FeedbackFilter => ({ tab: groupKey === "stars" ? "reviews" : "nps", label: labelOf(r), everyone, spec: { group: groupKey, clauses: r.clauses } });
  const shown = [...rows].sort((a, b) => a.p - b.p).slice(0, SHOWN);
  return (
    <div>
      <div style={{ display: "inline-flex", gap: 4, margin: "0 0 4px", flexWrap: "wrap" }}>
        {(["stars", "detractors"] as const).map((k) => <button key={k} aria-pressed={groupKey === k} onClick={() => setGroupKey(k)} style={pill(groupKey === k)}>{(data[k] as Group).title}</button>)}
      </div>
      <div className="card-sub" style={{ lineHeight: 1.5, marginBottom: 6 }}>
        Among {group.rows.toLocaleString("en-GB")} of {group.of.toLocaleString("en-GB")} rows, which {SECTION_TITLE[section].toLowerCase()} come up more than luck explains.
        {" "}{tests} tried, {rows.filter((r) => r.p * tests < 0.05).length} clear. <strong>Clear?</strong> is Yes when the chance of luck, counted over everything tried in this list, is under 5 %.
        {section === "products and themes" && " Here \"of\" is all the product's reviews or answers, and the chance is that of a product of that size holding so many of the theme's rows: a complaint is rare outside poor feedback, so a big product is not unusual just for having many."}
        {" "}Click a row to see its reviews or answers in the data below. {conditions.length === 0 ? "Covers all customers." : everyone ? "These rules are mined by Aito for all customers, not for the selected segment; the other lists follow the segment." : "Counted over the selected segment's reviews and answers."}
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
              <tr key={r.label} onClick={() => onSelect(selected?.label === labelOf(r) && selected.spec.group === groupKey ? null : filterOf(r))}
                  aria-selected={selected?.label === labelOf(r) && selected.spec.group === groupKey}
                  style={{ borderTop: "1px solid var(--border-light)", cursor: "pointer",
                           background: selected?.label === labelOf(r) && selected.spec.group === groupKey ? "rgba(0, 168, 150, 0.15)" : undefined }}>
                <td style={{ padding: "3px 6px 3px 0", overflowWrap: "anywhere" }}>{labelOf(r)}</td>
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
