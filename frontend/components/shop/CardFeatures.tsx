"use client";

import { useState } from "react";

import { renderMarkedText } from "@/components/prediction/WhyPopover";
import { apiFetch } from "@/lib/api";
import type { CardFeaturePattern, CardFeatures as CardFeaturesData } from "@/lib/types";

const SHOWN = 5;

/** The features behind a card's "products with this one's features" term, opened on demand: one
 *  Aito query (`_predict purchased` on the product's features), biggest effect first, the matched
 *  word of a text feature marked, the rest folded. Its numbers are its own: they don't multiply to
 *  the card's percentage. */
export default function CardFeatures({ sku, shopper, month, cart }: {
  sku: string; shopper: string; month: string; cart: string;
}) {
  const [data, setData] = useState<CardFeaturesData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [all, setAll] = useState(false);

  function load(open: boolean) {
    if (!open || data || error) return;
    apiFetch<CardFeaturesData>(`/api/shop/card-features?sku=${sku}&shopper=${shopper}&month=${month}&cart=${encodeURIComponent(cart)}`)
      .then(setData, (e) => setError(String(e?.message ?? e)));
  }

  return (
    <details style={{ marginTop: 10, borderTop: "1px solid var(--border-light)", paddingTop: 8 }}
             onToggle={(e) => load((e.target as HTMLDetailsElement).open)}>
      <summary style={{ cursor: "pointer", fontSize: 12, fontWeight: 600 }}>
        Which of the product&apos;s features?
      </summary>
      <div style={{ fontSize: 12, marginTop: 6 }}>
        {error && <div style={{ color: "var(--red)" }}>Couldn&apos;t load: {error}</div>}
        {!data && !error && <div className="card-sub">Asking Aito…</div>}
        {data && (
          <>
            <div className="card-sub" style={{ marginBottom: 6, lineHeight: 1.45 }}>
              A separate query: the product&apos;s features in place of its SKU, in this shopper&apos;s situation
              ({Math.round(data.base_p * 100)} % base → {Math.round(data.p * 100)} %). Its lifts don&apos;t multiply to the card&apos;s percentage, which knows the product itself, and features that select the same rows share one lift.
            </div>
            {(all ? data.patterns : data.patterns.slice(0, SHOWN)).map((p, i) => <Row key={i} pattern={p} />)}
            {data.patterns.length > SHOWN && (
              <button className="btn btn-ghost" style={{ fontSize: 11, padding: "2px 8px", marginTop: 4 }}
                      onClick={() => setAll(!all)}>
                {all ? "Show fewer" : `Show all ${data.patterns.length}`}
              </button>
            )}
            {data.joint.length > 0 && (
              <details style={{ marginTop: 6 }}>
                <summary style={{ cursor: "pointer", color: "var(--text-muted)" }}>
                  Estimated together by Aito ({data.joint.length}): these overlap the lifts above
                </summary>
                {data.joint.map((p, i) => <Row key={i} pattern={p} />)}
              </details>
            )}
          </>
        )}
      </div>
    </details>
  );
}

function Row({ pattern }: { pattern: CardFeaturePattern }) {
  const up = pattern.lift >= 1;
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 10, padding: "3px 0" }}>
      <div style={{ minWidth: 0 }}>
        {pattern.features.map((f, i) => (
          <div key={i}>
            {f.marked_text
              ? <><span style={{ color: "var(--text-muted)" }}>{f.label.split(" has the word")[0]}: </span>
                  <span style={{ fontStyle: "italic" }}>{renderMarkedText(f.marked_text, up)}</span></>
              : f.label}
          </div>
        ))}
      </div>
      <span style={{ fontFamily: "var(--mono)", fontWeight: 700, color: up ? "var(--cta)" : "var(--green)", flexShrink: 0 }}>
        {up ? "↑" : "↓"} {pattern.lift.toFixed(2)}×
      </span>
    </div>
  );
}
