"use client";

import { useState } from "react";

import type { ProductCandidate } from "@/lib/types";
import { monthLabel, words } from "./labels";

/**
 * Pick a product by typing part of its name (or brand), and a month.
 * The search narrows the list; the list is the choice, so a pasted link's
 * product shows as selected even before anything is typed.
 */
export default function ProductPicker({ products, sku, months, month, onSku, onMonth }: {
  products: ProductCandidate[];
  sku: string;
  months: string[];
  month: string;
  onSku: (sku: string) => void;
  onMonth: (month: string) => void;
}) {
  const [query, setQuery] = useState("");
  const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
  const matching = products.filter((p) =>
    terms.every((t) => `${p.name} ${p.brand} ${words(p.category)}`.toLowerCase().includes(t)));
  // The chosen product stays in the list, so the list still shows it.
  const listed = products.filter((p) => p.sku === sku || matching.includes(p));

  return (
    <div className="search-wrap" style={{ flexWrap: "wrap", gap: 8 }}>
      <input
        aria-label="Find a product by name" className="search-input" placeholder="Find a product: dental, Acana, litter…"
        value={query} onChange={(e) => setQuery(e.target.value)}
        style={{ paddingLeft: 12, width: 260 }}
      />
      <select
        id="sku-picker" aria-label="Product" className="search-input"
        style={{ paddingLeft: 12, width: "auto", minWidth: 300, maxWidth: "100%" }}
        value={sku} onChange={(e) => onSku(e.target.value)}
      >
        {groupByCategory(listed).map(([group, items]) => (
          <optgroup key={group} label={group}>
            {items.map((p) => <option key={p.sku} value={p.sku}>{p.name}</option>)}
          </optgroup>
        ))}
      </select>
      <span className="card-sub">{terms.length ? `${matching.length} ${matching.length === 1 ? "match" : "matches"}` : `${products.length} products`}</span>
      <select
        id="month-picker" aria-label="Month" className="search-input"
        style={{ paddingLeft: 12, width: "auto" }}
        value={month} onChange={(e) => onMonth(e.target.value)}
      >
        {[...months].reverse().map((m) => <option key={m} value={m}>{monthLabel(m)}</option>)}
      </select>
    </div>
  );
}

function groupByCategory(products: ProductCandidate[]): Array<[string, ProductCandidate[]]> {
  const groups = new Map<string, ProductCandidate[]>();
  for (const p of products) {
    const key = `${words(p.pet_type)} · ${words(p.category)}`;
    groups.set(key, [...(groups.get(key) ?? []), p]);
  }
  return [...groups.entries()];
}
