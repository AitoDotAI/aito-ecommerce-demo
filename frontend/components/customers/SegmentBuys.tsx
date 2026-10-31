"use client";

import { useState } from "react";

import type { PreferenceRow, ProfilesSummary } from "@/lib/customer-profiles";

const KINDS = [["categories", "Categories"], ["brands", "Brands"], ["products", "Products"]] as const;

/** What the selected way of shopping buys over-proportionally, against other customers who buy for the same pet. */
export default function SegmentBuys({ summary, selected }: { summary: ProfilesSummary; selected: string }) {
  const [pet, setPet] = useState<"dog" | "cat">("dog");
  const entry = summary.preferences[`${selected}|${pet}`];
  if (!summary.preferences[`${selected}|dog`] && !summary.preferences[`${selected}|cat`]) return null;
  return (
    <div className="card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 8 }}>
        <div className="card-title" style={{ margin: 0 }}>What they buy</div>
        <span style={{ display: "inline-flex", gap: 4 }}>
          {(["dog", "cat"] as const).map((p) => (
            <button key={p} aria-pressed={pet === p} onClick={() => setPet(p)} style={{
              cursor: "pointer", borderRadius: 12, padding: "2px 10px", font: "inherit", fontSize: 12, color: "var(--text)",
              border: `1px solid ${pet === p ? "var(--aito-teal)" : "var(--border)"}`,
              background: pet === p ? "rgba(0, 168, 150, 0.15)" : "transparent" }}>{p === "dog" ? "Dog owners" : "Cat owners"}</button>
          ))}
        </span>
      </div>
      <div className="card-sub" style={{ margin: "6px 0 8px", lineHeight: 1.5 }}>
        Of the customers in the segment, how many more points bought the item than other customers who buy for the same pet. Solid:
        larger than its 99.7 % margin. Faded: within it, only a hint. At product level most are hints: few customers buy each
        product and hundreds are compared.
      </div>
      {!entry && <div className="card-sub">Fewer than 30 {pet} owners in this segment.</div>}
      {entry && (
        <>
          <div className="card-sub" style={{ marginBottom: 6 }}>{entry.customers} customers against {entry.others}</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))", gap: 14 }}>
            {KINDS.map(([kind, title]) => (
              <div key={kind}>
                <div style={{ fontWeight: 600, marginBottom: 4 }}>{title}</div>
                {entry[kind].map((r) => <Item key={r.item} r={r} />)}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function Item({ r }: { r: PreferenceRow }) {
  return (
    <div style={{ fontSize: 13, margin: "3px 0", opacity: r.clear ? 1 : 0.45 }} title={`${r.buyers} buyers in the segment`}>
      {r.name ?? r.item}
      <span className="card-sub"> {r.points > 0 ? "+" : ""}{r.points} ±{r.margin_points} ({Math.round(r.share * 100)} % vs {Math.round(r.share_others * 100)} %)</span>
    </div>
  );
}
