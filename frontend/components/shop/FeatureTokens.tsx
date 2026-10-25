"use client";

import type { ShopItem } from "@/lib/types";

/** The tokens behind a card's "products with this one's features" term: the product's name and tags
 *  split into words, its brand, category and pet, and its state this month. Aito's `$why` gives the
 *  term as one lift and doesn't say which token carries it (asked of core), so no lift is shown per
 *  token: only that these are the features it stands for. */
export default function FeatureTokens({ features }: { features: ShopItem["features"] }) {
  return (
    <details style={{ marginTop: 6, fontSize: 11.5 }}>
      <summary style={{ cursor: "pointer", color: "var(--text-muted)" }}>Which features?</summary>
      <div className="card-sub" style={{ margin: "6px 0", lineHeight: 1.45 }}>
        The tokens Aito holds for this product. It gives their effect as one lift and doesn&apos;t yet say how
        much each carries.
      </div>
      {features.map((f) => (
        <div key={f.field} style={{ display: "flex", flexWrap: "wrap", alignItems: "baseline", gap: 4, padding: "2px 0" }}>
          <span style={{ color: "var(--text-muted)", minWidth: 78 }}>{f.field}</span>
          {f.tokens.map((t, i) => (
            <span key={i} style={{ background: "var(--bg)", border: "1px solid var(--border-light)", borderRadius: 4,
                                   padding: "0 5px", fontFamily: "var(--mono)", fontSize: 11 }}>{t}</span>
          ))}
        </div>
      ))}
    </details>
  );
}
