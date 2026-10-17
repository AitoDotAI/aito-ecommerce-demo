"use client";

import type { ShopReason } from "@/lib/types";

/** What makes this product likely for this shopper, in two kinds kept apart:
 *  Aito's reasons (lifts read from `$why`, teal) and plain facts (the offer,
 *  the stars, the household rule kept), which the data can't yet weigh. */
export default function ProductHighlights({ reasons, offerPct, rating, keepsRule }: {
  reasons: ShopReason[];
  offerPct: number | null;
  rating: number | null;
  keepsRule: boolean;
}) {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
      {offerPct !== null && <span className="shop-fact shop-fact-offer">−{Math.round(offerPct)} % this month</span>}
      {rating !== null && <span className="shop-fact" title="Average review rating">★ {rating.toFixed(1)}</span>}
      {keepsRule && <span className="shop-fact">Keeps their rule</span>}
      {reasons.map((r) => (
        <span key={r.label} className="shop-reason"
              title={`Aito: this multiplies the odds that this shopper buys it by ${r.lift.toFixed(2)}`}>
          {r.label} ×{r.lift.toFixed(1)}
        </span>
      ))}
    </div>
  );
}
