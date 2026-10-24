"use client";

import { fmtEur } from "@/lib/api";
import { lastLever } from "@/lib/sandbox";
import type { ScoreAdjustment, ShopItem } from "@/lib/types";
import ProductHighlights from "@/components/shop/ProductHighlights";
import VariantNote from "@/components/shop/VariantNote";

/** One recommended product: its name, price and offer, Aito's purchase
 *  probability for this shopper, and the strongest of Aito's reasons. For
 *  something they bought last order, how far
 *  that pulled it down. In a sandbox's 2026-05, a product a lever changed
 *  shows its re-scored score and that score's own explanation instead (ADR 0043). */
export default function ProductCard({ item, rank, onAdd, onOpen }: {
  item: ShopItem;
  rank?: number;           // its place in the grid, for the sandbox's rank change
  onAdd: () => void;
  onOpen: () => void;
}) {
  const shown = item.adjustment ? item.adjustment.score : item.p;
  return (
    <div className="card" style={{ padding: 12, display: "flex", flexDirection: "column", gap: 6 }}>
      <button
        onClick={onOpen}
        className="shop-card-name"
        aria-label={`Open ${item.name}`}
      >
        {item.name}
      </button>
      <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 6 }}>
        <span style={{ fontWeight: 600 }}>{fmtEur(item.price_eur, 2)}</span>
        {item.offer_pct !== null && <span className="shop-fact shop-fact-offer">−{Math.round(item.offer_pct)} % this month</span>}
        <VariantNote skus={item.same_name_skus} />
      </div>
      <div title={item.adjustment
        ? "This app's score: Aito's probability times the shop-wide lifts of the product's May state"
        : "Aito's probability that this shopper buys it when it is shown to them"}>
        <div style={{ height: 5, background: "var(--border-light)", borderRadius: 3 }}>
          <div style={{ width: `${Math.min(100, Math.round(shown * 100))}%`, height: "100%", background: "var(--cta)", borderRadius: 3 }} />
        </div>
        <div className="card-sub" style={{ marginTop: 2 }}>
          {item.adjustment
            ? <>Score {Math.round(shown * 100)} <RankChange item={item} rank={rank} /></>
            : `${Math.round(item.p * 100)} % buy it when shown`}
        </div>
      </div>
      {item.p_if_new !== null && (
        <div className="card-sub" style={{ color: "var(--red)" }}>
          Bought last order: {Math.round(item.p_if_new * 100)} % → {Math.round(item.p * 100)} %
        </div>
      )}
      {item.adjustment
        ? <AdjustedScore item={item} adjustment={item.adjustment} />
        : <ProductHighlights reasons={item.reasons.slice(0, 1)} offerPct={null} rating={null}
                             keepsRule={item.keeps_rule} />}
      <div style={{ display: "flex", gap: 6, marginTop: "auto" }}>
        <button className="btn" style={{ flex: 1 }} onClick={onAdd}>Add to cart</button>
        <button className="btn btn-ghost" onClick={onOpen} aria-label={`Details of ${item.name}`}>Details</button>
      </div>
    </div>
  );
}

/** The re-scored number's explanation: Aito's probability and its reasons,
 *  then this app's two shop-wide factors, multiplying out to the score. */
function AdjustedScore({ item, adjustment: a }: { item: ShopItem; adjustment: ScoreAdjustment }) {
  const stars = a.rating_band === "unrated" ? "No stars" : `${a.rating_band} stars`;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
        {a.offer_band !== "none" && (
          <span className="shop-lever" title="Aito's lift of this discount band over no offer, across every product">
            On offer ×{a.offer_factor.toFixed(1)}, learned across the shop
          </span>
        )}
        {a.rating_band !== a.rating_band_before && (
          <span className="shop-lever" title="Aito's lift of this star band over April's, across every product">
            {stars} ×{a.rating_factor.toFixed(2)}, learned across the shop
          </span>
        )}
      </div>
      <div className="card-sub" style={{ fontSize: 11, lineHeight: 1.5 }}>
        Aito&apos;s purchase probability {Math.round(a.aito_p * 100)} %
        {item.reasons.length > 0 && <> ({item.reasons.map((r) => `${r.label} ×${r.lift.toFixed(1)}`).join(", ")})</>}
        <br />× offer band lift ×{a.offer_factor.toFixed(2)} (shop-wide)
        <br />× star band lift ×{a.rating_factor.toFixed(2)} (shop-wide)
        <br />= score {Math.round(a.score * 100)}
      </div>
    </div>
  );
}

function RankChange({ item, rank }: { item: ShopItem; rank?: number }) {
  if (!rank || item.measured_rank === null || item.measured_rank === rank) return null;
  const moved = item.measured_rank - rank;
  const lever = lastLever();
  const since = lever?.sku === item.sku ? (lever.lever === "offer" ? "since the offer" : "since the review")
    : "with its May state";
  return (
    <span className={moved > 0 ? "shop-rank-up" : "shop-rank-down"}>
      {moved > 0 ? "↑" : "↓"} {Math.abs(moved)} {since}
    </span>
  );
}
