"use client";

import { useState } from "react";

import { ACQUISITION_TITLE, TRAIT_TITLE, type ProfilesSummary } from "@/lib/customer-profiles";

interface Related {
  kind: string; label: string; points: number; margin: number; clear: boolean; share: number; shareOthers: number; note?: string;
}

const LIST_LENGTH = 25;

/** Everything the selected segment is related to, as one list: the points more (or fewer) of it have each item than the rest. */
export function relatedItems(summary: ProfilesSummary, selected: string): Related[] {
  const rows: Related[] = [];
  for (const r of summary.relations.filter((x) => `${x.if.trait}:${x.if.value}` === selected)) {
    rows.push({ kind: "Shopping", label: `${TRAIT_TITLE[r.then.trait]}: ${r.then.value}`, points: r.points, margin: r.margin_points,
      clear: r.clear, share: r.share_with, shareOthers: r.share_without });
  }
  for (const pet of ["dog", "cat"] as const) {
    const entry = summary.preferences[`${selected}|${pet}`];
    if (!entry) continue;
    const owners = pet === "dog" ? "dog owners" : "cat owners";
    for (const [kind, title] of [["categories", "Category"], ["brands", "Brand"], ["products", "Product"]] as const) {
      for (const r of entry[kind]) {
        rows.push({ kind: title, label: `${r.name ?? r.item} (${owners})`, points: r.points, margin: r.margin_points, clear: r.clear,
          share: r.share, shareOthers: r.share_others });
      }
    }
  }
  for (const dimension of ["source", "landing", "landing_category"] as const) {
    for (const r of summary.acquisition[selected]?.[dimension] ?? []) {
      if (r.points === undefined) continue;
      rows.push({ kind: ACQUISITION_TITLE[dimension], label: r.value.replace("_", " "), points: r.points, margin: r.margin_points ?? 0,
        clear: Boolean(r.clear), share: r.share, shareOthers: r.share_others ?? 0 });
    }
  }
  return rows.sort((a, b) => Math.abs(b.points) - Math.abs(a.points));
}

export default function SegmentRelated({ summary, selected }: { summary: ProfilesSummary; selected: string }) {
  const [kind, setKind] = useState<string | null>(null);
  const [hints, setHints] = useState(false);
  const [more, setMore] = useState(false);
  if (selected === "all") return null;
  const all = relatedItems(summary, selected);
  const kinds = [...new Set(all.map((r) => r.kind))];
  const visible = all.filter((r) => (kind === null || r.kind === kind) && (hints || r.clear));
  const shown = more ? visible : visible.slice(0, LIST_LENGTH);
  const scale = Math.max(30, ...all.map((r) => Math.abs(r.points)));
  return (
    <div className="card">
      <div className="card-title">What goes with them</div>
      <div className="card-sub" style={{ marginBottom: 8, lineHeight: 1.5 }}>
        How many more (or fewer) points of this segment have each item than the customers outside it: other ways of shopping, what they buy
        (against customers who buy for the same pet) and where they came from (their first session). Only differences larger than their 99.7 %
        margin are listed; many pairs are compared, so the bar is high. At product level most are hints.
      </div>
      <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginBottom: 8 }}>
        {[null, ...kinds].map((k) => (
          <button key={k ?? "all"} aria-pressed={kind === k} onClick={() => { setKind(k); setMore(false); }} style={{
            cursor: "pointer", borderRadius: 12, padding: "2px 10px", font: "inherit", fontSize: 12, color: "var(--text)",
            border: `1px solid ${kind === k ? "var(--aito-teal)" : "var(--border)"}`,
            background: kind === k ? "rgba(0, 168, 150, 0.15)" : "transparent" }}>{k ?? "All"}</button>
        ))}
      </div>
      {visible.length === 0 && <div className="card-sub">Nothing clears the margin.</div>}
      {shown.map((r) => <Bar key={`${r.kind}:${r.label}`} r={r} scale={scale} />)}
      <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
        {visible.length > LIST_LENGTH && (
          <button className="btn btn-ghost" style={{ padding: "2px 10px", fontSize: 12 }} onClick={() => setMore(!more)}>
            {more ? "Fewer" : `Show all ${visible.length}`}
          </button>
        )}
        <button className="btn btn-ghost" style={{ padding: "2px 10px", fontSize: 12 }} onClick={() => setHints(!hints)}>
          {hints ? "Only the clear ones" : "Include hints"}
        </button>
      </div>
    </div>
  );
}

function Bar({ r, scale }: { r: Related; scale: number }) {
  const width = `${(Math.abs(r.points) / scale) * 50}%`;
  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(150px, 1.3fr) 1fr 150px", gap: 8, alignItems: "center", fontSize: 13, margin: "3px 0", opacity: r.clear ? 1 : 0.45 }}>
      <span><span className="card-sub">{r.kind} · </span>{r.label}</span>
      <span style={{ position: "relative", height: 12, background: "var(--border-light)", borderRadius: 3 }}>
        <span style={{ position: "absolute", left: "50%", top: 0, bottom: 0, width: 1, background: "var(--border)" }} />
        <span style={{ position: "absolute", top: 2, bottom: 2, borderRadius: 2, background: r.points >= 0 ? "var(--aito-teal)" : "var(--cta)",
          ...(r.points >= 0 ? { left: "50%", width } : { right: "50%", width }) }} />
      </span>
      <span className="card-sub">{r.points > 0 ? "+" : ""}{r.points} ±{r.margin} ({Math.round(r.share * 100)} % vs {Math.round(r.shareOthers * 100)} %)</span>
    </div>
  );
}
