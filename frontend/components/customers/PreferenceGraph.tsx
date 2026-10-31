"use client";

import { useState } from "react";

import { findSegment, type ProfilesSummary } from "@/lib/customer-profiles";

const GROUP_TITLES = ["Shopping", "Categories", "Brands"] as const;
const QUINTILE_NAMES = ["Top 20 %", "Next 20 %", "Middle 20 %", "Next 20 %", "Bottom 20 %"];

function group(variable: string): (typeof GROUP_TITLES)[number] {
  return variable.startsWith("category:") ? "Categories" : variable.startsWith("brand:") ? "Brands" : "Shopping";
}

/**
 * Customers ranked by how much they prefer something (their share of it over everyone's average), as a curve, with
 * the five fifths and where the selected segment sits along the ranking.
 */
export default function PreferenceGraph({ summary, selected }: { summary: ProfilesSummary; selected: string }) {
  const variables = Object.keys(summary.preference_ranking);
  const [variable, setVariable] = useState(variables.includes("offer") ? "offer" : variables[0]);
  const ranked = summary.preference_ranking[variable];
  if (!ranked) return null;
  const top = Math.max(...ranked.curve, 1.2);
  const found = findSegment(summary, selected);
  const baseShare = found ? found.segment.customers / summary.profiled : 0;
  const showSegment = selected !== "all" && found;
  return (
    <div className="card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 8 }}>
        <div className="card-title" style={{ margin: 0 }}>Preference ranking</div>
        <select value={variable} onChange={(e) => setVariable(e.target.value)} style={{ font: "inherit", padding: "3px 8px", maxWidth: "min(100%, 360px)" }}>
          {GROUP_TITLES.map((title) => (
            <optgroup key={title} label={title}>
              {variables.filter((v) => group(v) === title).map((v) => <option key={v} value={v}>{summary.preference_ranking[v].label}</option>)}
            </optgroup>
          ))}
        </select>
      </div>
      <div style={{ fontSize: 14, lineHeight: 1.55, margin: "8px 0" }}>
        Of {ranked.customers.toLocaleString("fi-FI")} customers ranked, the top fifth have <strong>{ranked.top_over_average}×</strong> the average
        share of this{ranked.top_over_bottom !== null
          ? <> and <strong>{ranked.top_over_bottom}×</strong> the bottom fifth&apos;s</>
          : <>; the bottom fifth buy none of it, so the ratio to them is undefined</>}.
      </div>
      <div className="card-sub">Each bar is 5 % of the customers, strongest preference first; the height is their lift on the average share ({(ranked.mean_share * 100).toFixed(0)} % of lines).</div>
      <div style={{ position: "relative", display: "flex", alignItems: "flex-end", gap: 2, height: 120, margin: "8px 0 4px", borderBottom: "1px solid var(--border)" }}>
        <div style={{ position: "absolute", left: 0, right: 0, bottom: `${(1 / top) * 100}%`, borderTop: "1px dashed var(--text-muted)" }} />
        <span className="card-sub" style={{ position: "absolute", right: 0, bottom: `calc(${(1 / top) * 100}% + 2px)`, fontSize: 11 }}>average</span>
        {ranked.curve.map((lift, i) => (
          <div key={i} title={`${i * 5}–${i * 5 + 5} %: ${lift}× the average`} style={{
            flex: 1, height: `${(lift / top) * 100}%`, background: i < 4 ? "var(--aito-teal)" : "var(--border)", borderRadius: "2px 2px 0 0" }} />
        ))}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 6, marginTop: 8 }}>
        {ranked.quintiles.map((q, i) => {
          const share = q.segment_share[selected];
          return (
            <div key={i} style={{ fontSize: 12 }}>
              <div style={{ fontWeight: 600 }}>{QUINTILE_NAMES[i]}</div>
              <div>{q.lift}× average</div>
              {showSegment && share !== undefined && (
                <>
                  <div style={{ height: 6, background: "var(--border-light)", borderRadius: 3, margin: "4px 0 2px", position: "relative" }}>
                    <div style={{ height: 6, width: `${Math.min(100, share * 100)}%`, background: "var(--cta)", borderRadius: 3 }} />
                    <div style={{ position: "absolute", top: -2, bottom: -2, left: `${baseShare * 100}%`, width: 1, background: "var(--text)" }} />
                  </div>
                  <div className="card-sub">{Math.round(share * 100)} % are in the segment</div>
                </>
              )}
            </div>
          );
        })}
      </div>
      {showSegment && found && (
        <div className="card-sub" style={{ marginTop: 6 }}>
          The line marks the segment&apos;s share of all profiled customers, {Math.round(baseShare * 100)} %: a bar past it means the segment is over-represented in that fifth.
        </div>
      )}
    </div>
  );
}
