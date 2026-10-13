"use client";

import type { ShopSuggestions } from "@/lib/types";

/** "Fill my usual basket" and "What's next for your pet": both predicted
 *  from this shopper's own history (src/shop_suggestions.py). */
export default function SuggestionsPanel({ suggestions, onAdd, onAddAll }: {
  suggestions: ShopSuggestions;
  onAdd: (sku: string) => void;
  onAddAll: (skus: string[]) => void;
}) {
  if (suggestions.no_history) {
    return <div className="card card-sub">No orders yet, so nothing to suggest from their history.</div>;
  }
  const owned = Object.entries(suggestions.owned)
    .map(([pet, kinds]) => `${pet.replace("_", " ")}: ${kinds.map((k) => k.replace("_", " ")).join(", ")}`);
  return (
    <div className="card">
      <div className="page-title" style={{ fontSize: 16, margin: 0 }}>Their usual basket</div>
      <div className="card-sub" style={{ marginBottom: 6 }}>
        What they buy again, each with Aito&apos;s probability (`skus.$feature` over their own orders)
      </div>
      {suggestions.usual.map((s) => (
        <Row key={s.sku} name={s.name} p={s.p} onAdd={() => onAdd(s.sku)} />
      ))}
      {suggestions.usual.length > 0 && (
        <button className="btn" style={{ marginTop: 8 }}
                onClick={() => onAddAll(suggestions.usual.filter((s) => s.p >= 0.15).map((s) => s.sku))}>
          Fill my usual basket
        </button>
      )}

      <div className="page-title" style={{ fontSize: 16, margin: "16px 0 0" }}>What&apos;s next for their pet</div>
      <div className="card-sub" style={{ marginBottom: 6 }}>
        {owned.length ? `Owns ${owned.join("; ")}.` : "No kit bought yet."} Next, from shoppers who owned the same.
      </div>
      {suggestions.next_for_pet.length === 0 && (
        <div className="card-sub">Nothing left to add to the kit.</div>
      )}
      {suggestions.next_for_pet.map((s) => (
        <Row key={s.sku} name={s.name} p={s.p} onAdd={() => onAdd(s.sku)} />
      ))}
    </div>
  );
}

function Row({ name, p, onAdd }: { name: string; p: number; onAdd: () => void }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 8, padding: "4px 0", fontSize: 13 }}>
      <span>{name}</span>
      <span style={{ whiteSpace: "nowrap" }}>
        <span className="card-sub">{Math.round(p * 100)} %</span>
        <button className="btn btn-ghost" style={{ marginLeft: 6, padding: "0 8px" }} onClick={onAdd}
                aria-label={`Add ${name}`}>+</button>
      </span>
    </div>
  );
}
