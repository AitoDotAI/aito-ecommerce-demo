"use client";

import { useState } from "react";

import { TRAIT_TITLE, type ProfilesSummary, type Relation } from "@/lib/customer-profiles";

const key = (r: { trait: string; value: string }) => `${r.trait}:${r.value}`;

/** How the profile variables relate: among customers with one trait, how many more points have another than those without. */
export default function RelationsCard({ summary }: { summary: ProfilesSummary }) {
  const starts = [...new Map(summary.relations.map((r) => [key(r.if), r.if])).values()];
  const [chosen, setChosen] = useState(key(starts.find((s) => s.value === "mostly") ?? starts[0]));
  const shown = summary.relations.filter((r) => key(r.if) === chosen).sort((a, b) => b.points - a.points);
  const from = starts.find((s) => key(s) === chosen);
  const scale = Math.max(30, ...shown.map((r) => Math.abs(r.points)));
  return (
    <div className="card">
      <div className="card-title">How the profile variables relate</div>
      <div className="card-sub" style={{ marginBottom: 8 }}>
        Of the customers who are in the group below, how many more (or fewer) points have each other trait than the customers
        outside it. Solid: larger than its 99.7 % margin (many pairs are compared, so the bar is high). Faded: within the margin, not a result.
        Diet tags are left out: a diet belongs to a kind of pet, so it would show only the catalogue.
      </div>
      <label>
        Customers who are{" "}
        <select value={chosen} onChange={(e) => setChosen(e.target.value)} style={{ font: "inherit", padding: "2px 6px" }}>
          {starts.map((s) => <option key={key(s)} value={key(s)}>{TRAIT_TITLE[s.trait]}: {s.value}</option>)}
        </select>
      </label>
      {from && <span className="card-sub"> ({shown[0]?.customers_with} customers)</span>}
      <div style={{ marginTop: 10 }}>
        {shown.map((r) => <RelationBar key={key(r.then)} r={r} scale={scale} />)}
      </div>
    </div>
  );
}

function RelationBar({ r, scale }: { r: Relation; scale: number }) {
  const width = `${(Math.abs(r.points) / scale) * 50}%`;
  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(170px, 1fr) 2fr 210px", gap: 8, alignItems: "center", fontSize: 13, margin: "3px 0", opacity: r.clear ? 1 : 0.45 }}>
      <span>{TRAIT_TITLE[r.then.trait]}: {r.then.value}</span>
      <span style={{ position: "relative", height: 14, background: "var(--border-light)", borderRadius: 3 }}>
        <span style={{ position: "absolute", left: "50%", top: 0, bottom: 0, width: 1, background: "var(--border)" }} />
        <span style={{ position: "absolute", top: 2, bottom: 2, borderRadius: 2, background: r.points >= 0 ? "var(--aito-teal)" : "var(--cta)",
          ...(r.points >= 0 ? { left: "50%", width } : { right: "50%", width }) }} />
      </span>
      <span className="card-sub">{r.points > 0 ? "+" : ""}{r.points} <span>±{r.margin_points}</span> ({Math.round(r.share_with * 100)} % vs {Math.round(r.share_without * 100)} %)</span>
    </div>
  );
}
