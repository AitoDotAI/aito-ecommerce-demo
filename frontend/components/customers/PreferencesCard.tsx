"use client";

import { useState } from "react";

import { TRAIT_TITLE, type PreferenceRow, type ProfilesSummary } from "@/lib/customer-profiles";

const KINDS: [keyof Pick<import("@/lib/customer-profiles").PreferenceGroup, "categories" | "brands" | "products">, string][] = [
  ["categories", "Categories"], ["brands", "Brands"], ["products", "Products"],
];

/** What each way of shopping buys over-proportionally, against other customers who buy for the same pet. */
export default function PreferencesCard({ summary }: { summary: ProfilesSummary }) {
  const [pet, setPet] = useState("dog");
  const groups = Object.entries(summary.preferences).filter(([, g]) => g.pet === pet);
  const [segment, setSegment] = useState("offer:mostly");
  const entry = summary.preferences[`${segment}|${pet}`];
  const options = groups.map(([k]) => k.split("|")[0]);
  const label = (k: string) => { const [trait, value] = k.split(":"); return `${TRAIT_TITLE[trait]}: ${value}`; };
  return (
    <div className="card">
      <div className="card-title">What each group buys</div>
      <div className="card-sub" style={{ marginBottom: 8 }}>
        Of the customers in the group, how many more points bought the item than other customers who buy for the same pet
        (so a dog owner is not compared with a cat owner). Solid: larger than its 99.7 % margin. Faded: within the margin, so
        only a hint. At product level most are hints: a few customers buy each product, and hundreds of products are compared.
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 10 }}>
        {["dog", "cat"].map((p) => (
          <button key={p} aria-pressed={pet === p} onClick={() => setPet(p)} style={{
            cursor: "pointer", borderRadius: 14, padding: "3px 12px", font: "inherit", color: "var(--text)",
            border: `1px solid ${pet === p ? "var(--aito-teal)" : "var(--border)"}`,
            background: pet === p ? "rgba(0, 168, 150, 0.15)" : "transparent" }}>{p === "dog" ? "Dog owners" : "Cat owners"}</button>
        ))}
        <select value={options.includes(segment) ? segment : options[0]} onChange={(e) => setSegment(e.target.value)}
          style={{ font: "inherit", padding: "2px 6px" }}>
          {options.map((k) => <option key={k} value={k}>{label(k)}</option>)}
        </select>
        {entry && <span className="card-sub">{entry.customers} customers against {entry.others}</span>}
      </div>
      {entry && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(250px, 1fr))", gap: 16 }}>
          {KINDS.map(([kind, title]) => (
            <div key={kind}>
              <div style={{ fontWeight: 600, marginBottom: 4 }}>{title}</div>
              {entry[kind].map((r) => <ItemRow key={r.item} r={r} />)}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ItemRow({ r }: { r: PreferenceRow }) {
  return (
    <div style={{ fontSize: 13, margin: "3px 0", opacity: r.clear ? 1 : 0.45 }} title={`${r.buyers} buyers in the group`}>
      {r.name ?? r.item}
      <span className="card-sub"> {r.points > 0 ? "+" : ""}{r.points} <span>±{r.margin_points}</span> ({Math.round(r.share * 100)} % vs {Math.round(r.share_others * 100)} %)</span>
    </div>
  );
}
