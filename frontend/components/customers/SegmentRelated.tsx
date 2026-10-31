"use client";

import { useState } from "react";

import Confidence from "@/components/customers/Confidence";
import { TRAIT_TITLE, type SegmentView } from "@/lib/customer-profiles";

interface Related {
  kind: string; label: string; points: number; margin: number; clear: boolean; share: number; shareOthers: number; note?: string;
}

const LIST_LENGTH = 25;

/** What else the selected segment prefers, as one list: the points more (or fewer) of it have each item than the rest. */
export function relatedItems(view: SegmentView): Related[] {
  const rows: Related[] = [];
  for (const r of view.relations ?? []) {
    rows.push({ kind: "Shopping", label: `${TRAIT_TITLE[r.then.trait]}: ${r.then.value}`, points: r.points, margin: r.margin_points,
      clear: r.clear, share: r.share_with, shareOthers: r.share_without });
  }
  for (const [pet, entry] of Object.entries(view.preferences ?? {})) {
    const owners = pet === "dog" ? "dog owners" : "cat owners";
    for (const [kind, title] of [["categories", "Category"], ["brands", "Brand"], ["products", "Product"]] as const) {
      for (const r of entry[kind]) {
        rows.push({ kind: title, label: `${r.name ?? r.item} (${owners})`, points: r.points, margin: r.margin_points, clear: r.clear,
          share: r.share, shareOthers: r.share_others });
      }
    }
  }
  return rows.sort((a, b) => Number(b.clear) - Number(a.clear) || Math.abs(b.points) - Math.abs(a.points));
}

export default function SegmentRelated({ view }: { view: SegmentView }) {
  const [kind, setKind] = useState<string | null>(null);
  const [more, setMore] = useState(false);
  if (view.conditions.length === 0) return <div className="card card-sub">Pick a segment to see what goes with it.</div>;
  const all = relatedItems(view);
  const kinds = [...new Set(all.map((r) => r.kind))];
  const visible = all.filter((r) => (kind === null || r.kind === kind));
  const shown = more ? visible : visible.slice(0, LIST_LENGTH);
  const scale = Math.max(30, ...all.map((r) => Math.abs(r.points)));
  return (
    <div className="card">
      <div className="card-title">Their other preferences</div>
      <div className="card-sub" style={{ marginBottom: 8, lineHeight: 1.5 }}>
        How many more (or fewer) points of this segment have each item than the customers outside it: other ways of shopping and what they buy
        (against customers who buy for the same pet). The confidence column is the difference divided
        by its 99.7 % margin: above 1× it is larger than chance would give. Many pairs are compared, so the bar is high, and at product level
        most sit below it. Clear ones first.
      </div>
      <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginBottom: 8 }}>
        {[null, ...kinds].map((k) => (
          <button key={k ?? "all"} aria-pressed={kind === k} onClick={() => { setKind(k); setMore(false); }} style={{
            cursor: "pointer", borderRadius: 12, padding: "2px 10px", font: "inherit", fontSize: 12, color: "var(--text)",
            border: `1px solid ${kind === k ? "var(--aito-teal)" : "var(--border)"}`,
            background: kind === k ? "rgba(0, 168, 150, 0.15)" : "transparent" }}>{k ?? "All"}</button>
        ))}
      </div>
      {visible.length === 0 && <div className="card-sub">Nothing to show.</div>}
      {shown.map((r) => <Bar key={`${r.kind}:${r.label}`} r={r} scale={scale} />)}
      <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
        {visible.length > LIST_LENGTH && (
          <button className="btn btn-ghost" style={{ padding: "2px 10px", fontSize: 12 }} onClick={() => setMore(!more)}>
            {more ? "Fewer" : `Show all ${visible.length}`}
          </button>
        )}
      </div>
    </div>
  );
}

function Bar({ r, scale }: { r: Related; scale: number }) {
  const width = `${(Math.abs(r.points) / scale) * 50}%`;
  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(120px, 1.3fr) minmax(60px, 0.8fr) minmax(110px, 140px) 44px", gap: 8, alignItems: "center", fontSize: 13, margin: "3px 0", }}>
      <span><span className="card-sub">{r.kind} · </span>{r.label}</span>
      <span style={{ position: "relative", height: 12, background: "var(--border-light)", borderRadius: 3 }}>
        <span style={{ position: "absolute", left: "50%", top: 0, bottom: 0, width: 1, background: "var(--border)" }} />
        <span style={{ position: "absolute", top: 2, bottom: 2, borderRadius: 2, background: r.points >= 0 ? "var(--aito-teal)" : "var(--cta)",
          ...(r.points >= 0 ? { left: "50%", width } : { right: "50%", width }) }} />
      </span>
      <span className="card-sub">{r.points > 0 ? "+" : ""}{r.points} ±{r.margin} ({Math.round(r.share * 100)} % vs {Math.round(r.shareOthers * 100)} %)</span>
      <Confidence points={r.points} margin={r.margin} />
    </div>
  );
}
