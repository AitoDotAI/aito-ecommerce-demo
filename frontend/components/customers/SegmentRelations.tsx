"use client";

import { useState } from "react";

import { TRAIT_TITLE, type ProfilesSummary, type Relation } from "@/lib/customer-profiles";

/** How the selected segment relates to the other variables: how many more points of it have each other trait than the rest. */
export default function SegmentRelations({ summary, selected }: { summary: ProfilesSummary; selected: string }) {
  const [showAll, setShowAll] = useState(false);
  const all = summary.relations.filter((r) => `${r.if.trait}:${r.if.value}` === selected).sort((a, b) => b.points - a.points);
  if (all.length === 0) {
    return (
      <div className="card card-sub">
        Relations are shown for ways of shopping and pets. Diet tags are left out: a diet belongs to a kind of pet, so it would only show the catalogue.
      </div>
    );
  }
  const shown = showAll ? all : all.filter((r) => r.clear);
  const scale = Math.max(30, ...all.map((r) => Math.abs(r.points)));
  return (
    <div className="card">
      <div className="card-title">How it relates to the other variables</div>
      <div className="card-sub" style={{ marginBottom: 8, lineHeight: 1.5 }}>
        Of these {all[0].customers_with} customers, how many more (or fewer) points have each trait than the customers outside the segment.
        Only differences larger than their 99.7 % margin are listed (many pairs are compared, so the bar is high).
      </div>
      {shown.length === 0 && <div className="card-sub">Nothing clears the margin.</div>}
      {shown.map((r) => <Bar key={`${r.then.trait}:${r.then.value}`} r={r} scale={scale} />)}
      <button className="btn btn-ghost" style={{ marginTop: 6, padding: "2px 10px", fontSize: 12 }} onClick={() => setShowAll(!showAll)}>
        {showAll ? "Only the clear ones" : `Show all ${all.length}`}
      </button>
    </div>
  );
}

function Bar({ r, scale }: { r: Relation; scale: number }) {
  const width = `${(Math.abs(r.points) / scale) * 50}%`;
  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(140px, 1fr) 1.5fr 150px", gap: 8, alignItems: "center", fontSize: 13, margin: "3px 0", opacity: r.clear ? 1 : 0.45 }}>
      <span>{TRAIT_TITLE[r.then.trait]}: {r.then.value}</span>
      <span style={{ position: "relative", height: 12, background: "var(--border-light)", borderRadius: 3 }}>
        <span style={{ position: "absolute", left: "50%", top: 0, bottom: 0, width: 1, background: "var(--border)" }} />
        <span style={{ position: "absolute", top: 2, bottom: 2, borderRadius: 2, background: r.points >= 0 ? "var(--aito-teal)" : "var(--cta)",
          ...(r.points >= 0 ? { left: "50%", width } : { right: "50%", width }) }} />
      </span>
      <span className="card-sub">{r.points > 0 ? "+" : ""}{r.points} ±{r.margin_points} ({Math.round(r.share_with * 100)} % vs {Math.round(r.share_without * 100)} %)</span>
    </div>
  );
}
