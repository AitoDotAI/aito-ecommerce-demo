"use client";

import { fmtEur } from "@/lib/api";
import type { ShopItem } from "@/lib/types";
import ProductHighlights from "@/components/shop/ProductHighlights";

/** One recommended product: Aito's purchase probability for this shopper,
 *  why, and, for something they bought last order, how far that pulled it down. */
export default function ProductCard({ item, onAdd, onOpen }: {
  item: ShopItem;
  onAdd: () => void;
  onOpen: () => void;
}) {
  return (
    <div className="card" style={{ padding: 12, display: "flex", flexDirection: "column", gap: 6 }}>
      <button
        onClick={onOpen}
        className="shop-card-name"
        aria-label={`Open ${item.name}`}
      >
        {item.name}
      </button>
      <div className="card-sub">
        {item.pet_type.replace("_", " ")} · {item.category.replace("-", " ")} · {fmtEur(item.price_eur, 2)}
      </div>
      <div title="Aito's probability that this shopper buys it when it is shown to them">
        <div style={{ height: 5, background: "var(--border-light)", borderRadius: 3 }}>
          <div style={{ width: `${Math.round(item.p * 100)}%`, height: "100%", background: "var(--cta)", borderRadius: 3 }} />
        </div>
        <div className="card-sub" style={{ marginTop: 2 }}>{Math.round(item.p * 100)} % buy it when shown</div>
      </div>
      {item.p_if_new !== null && (
        <div className="card-sub" style={{ color: "var(--red)" }}>
          Bought last order: {Math.round(item.p_if_new * 100)} % → {Math.round(item.p * 100)} %
        </div>
      )}
      <ProductHighlights reasons={item.reasons} offerPct={item.offer_pct} rating={item.avg_rating}
                         keepsRule={item.keeps_rule} />
      <div style={{ display: "flex", gap: 6, marginTop: "auto" }}>
        <button className="btn" style={{ flex: 1 }} onClick={onAdd}>Add to cart</button>
        <button className="btn btn-ghost" onClick={onOpen} aria-label={`Details of ${item.name}`}>Details</button>
      </div>
    </div>
  );
}
