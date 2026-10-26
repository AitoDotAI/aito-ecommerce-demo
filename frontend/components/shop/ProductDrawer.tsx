"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";

import { apiFetch, fmtEur } from "@/lib/api";
import { useSandboxEnv, withSandbox } from "@/lib/sandbox";
import type { ShopProductDrawer } from "@/lib/types";
import ProductHighlights from "@/components/shop/ProductHighlights";
import VariantNote from "@/components/shop/VariantNote";

/** A product, opened: its details, what this shopper would buy instead
 *  (ranked by Aito, with why), what is often in the same basket (from all
 *  orders), and when this shopper bought it (their own history). */
export default function ProductDrawer({ sku, shopper, month, cart, onClose, onAdd, onOpen }: {
  sku: string;
  shopper: string;
  month: string;
  cart: string;           // the cart's SKUs, comma-separated: context for the alternatives
  onClose: () => void;
  onAdd: (sku: string) => void;
  onOpen: (sku: string) => void;
}) {
  const sandbox = useSandboxEnv();
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
    apiFetch<ShopProductDrawer>(
      `/api/shop/product?sku=${encodeURIComponent(sku)}&shopper=${shopper}&month=${month}&cart=${encodeURIComponent(cart)}`)
      .then((d) => { if (current) setDrawer(d); }, (e) => { if (current) setError(String(e)); });
    return () => { current = false; };
  }, [sku, shopper, month, cart]);

  // A modal over a backdrop, above the Aito side panel (which would cover a
  // drawer pinned to the right edge). A click on the backdrop closes it.
  const product = drawer?.product;
  return (
    <div className="pdp-backdrop" onClick={onClose}>
    <div role="dialog" aria-modal="true" aria-label="Product" className="card pdp" onClick={(e) => e.stopPropagation()}>
      <header className="pdp-head">
        <div>
          <h2 className="pdp-name">{product?.name ?? sku}</h2>
          {product && (
            <div className="pdp-crumbs">
              {product.brand} <span>›</span> {product.pet_type.replace("_", " ")} <span>›</span> {product.category.replace("-", " ")}
            </div>
          )}
        </div>
        <button ref={closeButton} className="btn btn-ghost" onClick={onClose} aria-label="Close product">×</button>
      </header>
      {error && <div className="card-sub" style={{ color: "var(--red)" }}>Couldn&apos;t load: {error}</div>}
      {!drawer && !error && <div style={{ height: 120, background: "var(--border-light)", borderRadius: 4 }} />}
      {drawer && product && (
        <>
          <section className="pdp-buy">
            <div>
              <div className="pdp-price">{fmtEur(product.price_eur, 2)}</div>
              <ProductHighlights reasons={[]} offerPct={drawer.offer_pct} rating={product.avg_rating} keepsRule={false} />
            </div>
            <div className="pdp-actions">
              <button className="btn" onClick={() => onAdd(product.sku)}>Add to cart</button>
              <Link href={withSandbox(`/product/?sku=${encodeURIComponent(product.sku)}&month=${month}`, sandbox)}>
                Owner view of this product →
              </Link>
            </div>
          </section>
          {(product.dietary || product.tags) && (
            <div className="pdp-facts">
              {product.dietary && <span className="pdp-fact"><b>Diet</b> {product.dietary}</span>}
              {product.tags.split(/\s+/).filter(Boolean).map((tag) => <span key={tag} className="pdp-fact">{tag}</span>)}
            </div>
          )}

          <section className="pdp-section">
            <h3>Instead, this shopper might buy</h3>
            <p>The same kind of product, ranked by Aito for them, with why</p>
            {drawer.alternatives.length === 0 && <p>No other product of this kind to offer them.</p>}
            <div className="pdp-alts">
              {drawer.alternatives.map((a) => (
                <div key={a.sku} className="pdp-alt">
                  <button className="shop-card-name" onClick={() => onOpen(a.sku)} aria-label={`Open ${a.name}`}>{a.name}</button>
                  <VariantNote skus={a.same_name_skus} />
                  <div className="pdp-alt-row">
                    <b>{fmtEur(a.price_eur, 2)}</b>
                    <button className="btn btn-ghost" onClick={() => onAdd(a.sku)} aria-label={`Add ${a.name}`}>+ Add</button>
                  </div>
                  <Meter value={a.p} label={`${Math.round(a.p * 100)} % buy it when shown`} />
                  <ProductHighlights reasons={a.reasons} offerPct={a.offer_pct} rating={a.avg_rating} keepsRule={a.keeps_rule} />
                </div>
              ))}
            </div>
          </section>

          <section className="pdp-section">
            <h3>Often in the same basket</h3>
            <p>From all orders; pairs seen in at least 5 orders, more often than chance</p>
            {drawer.same_basket.length === 0 && <p>No pair is common enough to show.</p>}
            {drawer.same_basket.map((p) => (
              <div key={p.sku} className="pdp-pair">
                <span className="shop-reason" title="How much more often than chance the two are bought together">{p.lift.toFixed(1)}×</span>
                <span className="pdp-pair-name">
                  <button className="shop-card-name" style={{ fontWeight: 400 }} onClick={() => onOpen(p.sku)}
                          aria-label={`Open ${p.name}`}>{p.name}</button>
                  <VariantNote skus={p.same_name_skus} />
                  <Meter value={p.together / p.orders_with_it} label={`${p.together} of ${p.orders_with_it} orders with it`} />
                </span>
                <button className="btn btn-ghost" onClick={() => onAdd(p.sku)} aria-label={`Add ${p.name}`}>+ Add</button>
              </div>
            ))}
          </section>

          <section className="pdp-section">
            <h3>In this shopper&apos;s orders</h3>
            {drawer.your_orders.length ? (
              <div className="pdp-facts">
                {drawer.your_orders.map((m) => <span key={m} className="pdp-fact">{m}</span>)}
                <p style={{ margin: 0 }}>their history before {month}, not a prediction</p>
              </div>
            ) : <p>Not bought by this shopper before {month}.</p>}
          </section>
        </>
      )}
    </div>
    </div>
  );
}

/** A share as a thin bar with its caption: how likely, or how often. */
function Meter({ value, label }: { value: number; label: string }) {
  return (
    <div className="pdp-meter">
      <div><div style={{ width: `${Math.min(100, Math.max(2, Math.round(value * 100)))}%` }} /></div>
      <span>{label}</span>
    </div>
  );
}
