"use client";

import { useEffect, useRef, useState } from "react";

import { apiFetch, fmtEur } from "@/lib/api";
import type { ShopProductDrawer } from "@/lib/types";

/** A product, opened: what is often in the same basket (from all orders),
 *  and when this shopper bought it (their own history). */
export default function ProductDrawer({ sku, shopper, month, onClose, onAdd }: {
  sku: string;
  shopper: string;
  month: string;
  onClose: () => void;
  onAdd: (sku: string) => void;
}) {
  const [drawer, setDrawer] = useState<ShopProductDrawer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const closeButton = useRef<HTMLButtonElement>(null);

  // A modal: focus moves in, Escape closes it, and focus returns to where it was.
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    closeButton.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => { window.removeEventListener("keydown", onKey); opener?.focus(); };
  }, [onClose]);

  useEffect(() => {
    let current = true;
    setDrawer(null);
    setError(null);
    apiFetch<ShopProductDrawer>(`/api/shop/product?sku=${encodeURIComponent(sku)}&shopper=${shopper}&month=${month}`)
      .then((d) => { if (current) setDrawer(d); }, (e) => { if (current) setError(String(e)); });
    return () => { current = false; };
  }, [sku, shopper, month]);

  // A modal over a backdrop, above the Aito side panel (which would cover a
  // drawer pinned to the right edge). A click on the backdrop closes it.
  return (
    <div onClick={onClose}
         style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.25)", zIndex: 1000,
                  display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
    <div role="dialog" aria-modal="true" aria-label="Product" className="card" onClick={(e) => e.stopPropagation()}
         style={{ width: "min(420px, 100%)", maxHeight: "80vh", overflowY: "auto",
                  boxShadow: "0 8px 30px rgba(0,0,0,0.25)" }}>
      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <div className="page-title" style={{ fontSize: 16, margin: 0 }}>{drawer?.product.name ?? sku}</div>
        <button ref={closeButton} className="btn btn-ghost" onClick={onClose} aria-label="Close product">×</button>
      </div>
      {error && <div className="card-sub" style={{ color: "var(--red)" }}>Couldn&apos;t load: {error}</div>}
      {!drawer && !error && <div style={{ height: 120, background: "var(--border-light)", borderRadius: 4 }} />}
      {drawer && (
        <>
          <div className="card-sub">{drawer.product.brand} · {fmtEur(drawer.product.price_eur, 2)}</div>
          <button className="btn" style={{ margin: "10px 0" }} onClick={() => onAdd(drawer.product.sku)}>Add to cart</button>

          <div style={{ fontWeight: 600, fontSize: 13, marginTop: 6 }}>Often in the same basket</div>
          <div className="card-sub" style={{ marginBottom: 4 }}>
            From all orders; pairs seen in at least 5 orders, more often than chance
          </div>
          {drawer.same_basket.length === 0 && <div className="card-sub">No pair is common enough to show.</div>}
          {drawer.same_basket.map((p) => (
            <div key={p.sku} style={{ display: "flex", justifyContent: "space-between", fontSize: 13, padding: "3px 0" }}>
              <span>{p.name}</span>
              <span className="card-sub" style={{ whiteSpace: "nowrap" }}>
                {p.lift.toFixed(1)}× · {p.together} of {p.orders_with_it}
                <button className="btn btn-ghost" style={{ marginLeft: 6, padding: "0 6px" }}
                        onClick={() => onAdd(p.sku)} aria-label={`Add ${p.name}`}>+</button>
              </span>
            </div>
          ))}

          <div style={{ fontWeight: 600, fontSize: 13, marginTop: 12 }}>In this shopper&apos;s orders</div>
          <div className="card-sub">
            {drawer.your_orders.length
              ? `Bought in ${drawer.your_orders.join(", ")} (their history before ${month}, not a prediction).`
              : `Not bought by this shopper before ${month}.`}
          </div>
        </>
      )}
    </div>
    </div>
  );
}
