"use client";

import type { ShopSuggestions } from "@/lib/types";

/** Two of the Shop's three views, one per intent (ADR 0033, amendment of
 *  2026-10-21): "Buy again" (the routine) and "Next for their kit" (the
 *  kit's next step). Both are predicted from this shopper's own orders
 *  (src/shop_suggestions.py); "Picked for you" is the grid below them. */
// "Fill my usual basket" adds what they buy at least this often.
const FILL_AT = 0.15;

export default function SuggestionsPanel({ suggestions, month, onAdd, onAddAll }: {
  suggestions: ShopSuggestions;
  month: string;
  onAdd: (sku: string) => void;
  onAddAll: (skus: string[]) => void;
}) {
  if (suggestions.no_history) {
    return <div className="card card-sub">No orders before {month}: nothing to buy again or to add to a kit yet.</div>;
  }
  const owned = Object.entries(suggestions.owned)
    .map(([pet, kinds]) => `${pet.replace("_", " ")}: ${kinds.map((k) => k.replace("_", " ")).join(", ")}`);
  return (
    <div className="shop-shelves">
      <div className="card">
        <div className="page-title" style={{ fontSize: 16, margin: 0 }}>Buy again</div>
        <div className="card-sub" style={{ marginBottom: 6 }}>
          Their routine: what they buy again from their orders before {month}, each with Aito&apos;s
          probability (`skus.$feature` over those orders)
        </div>
        {suggestions.usual.length === 0 && <div className="card-sub">No routine yet.</div>}
        {suggestions.usual.map((s) => (
          <Row key={s.sku} name={s.name} p={s.p} onAdd={() => onAdd(s.sku)} />
        ))}
        {suggestions.usual.length > 0 && (
          <div style={{ marginTop: 8 }}>
            <button className="btn"
                    onClick={() => onAddAll(suggestions.usual.filter((s) => s.p >= FILL_AT).map((s) => s.sku))}>
              Fill my usual basket
            </button>
            <span className="card-sub" style={{ marginLeft: 8 }}>adds those at {Math.round(FILL_AT * 100)} % or more</span>
          </div>
        )}
      </div>

      <div className="card">
        <div className="page-title" style={{ fontSize: 16, margin: 0 }}>Next for their kit</div>
        <div className="card-sub" style={{ marginBottom: 6 }}>
          {owned.length ? `Owns ${owned.join("; ")}.` : "No kit bought yet."} Next, from shoppers who owned the same.
        </div>
        {suggestions.next_for_pet.length === 0 && (
          <div className="card-sub">{owned.length ? "Nothing left to add to the kit." : "Nothing to complete."}</div>
        )}
        {suggestions.next_for_pet.map((s) => (
          <Row key={s.sku} name={s.name} p={s.p} onAdd={() => onAdd(s.sku)} />
        ))}
      </div>
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
