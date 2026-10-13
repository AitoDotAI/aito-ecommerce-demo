"use client";

import { fmtEur } from "@/lib/api";
import type { ShopProduct } from "@/lib/types";

/** The cart. It lives in the URL, and every change re-ranks the grid. */
export default function CartPanel({ cart, onRemove, onClear }: {
  cart: ShopProduct[];
  onRemove: (sku: string) => void;
  onClear: () => void;
}) {
  const total = cart.reduce((sum, p) => sum + p.price_eur, 0);
  return (
    <div className="card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <div className="page-title" style={{ fontSize: 16, margin: 0 }}>Cart</div>
        {cart.length > 0 && <button className="btn btn-ghost" onClick={onClear}>Empty</button>}
      </div>
      {cart.length === 0 && (
        <div className="card-sub" style={{ marginTop: 8 }}>
          Empty. Add something and watch the recommendations change.
        </div>
      )}
      {cart.map((p) => (
        <div key={p.sku} style={{ display: "flex", justifyContent: "space-between", gap: 8, padding: "6px 0", fontSize: 13 }}>
          <span>{p.name}</span>
          <span style={{ whiteSpace: "nowrap" }}>
            {fmtEur(p.price_eur, 2)}
            <button className="btn btn-ghost" style={{ marginLeft: 6, padding: "0 6px" }}
                    onClick={() => onRemove(p.sku)} aria-label={`Remove ${p.name}`}>×</button>
          </span>
        </div>
      ))}
      {cart.length > 0 && (
        <div style={{ borderTop: "1px solid var(--border-light)", marginTop: 6, paddingTop: 6, fontWeight: 600 }}>
          {fmtEur(total, 2)}
        </div>
      )}
    </div>
  );
}
