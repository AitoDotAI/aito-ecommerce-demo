"use client";

import { More, Threshold, fmt, pct } from "@/components/shop-analytics/LiftParts";
import type { ShopAnalyticsPair, ShopBasketSection } from "@/lib/types";

const TOGETHER_SHOWN = 8;
const APART_SHOWN = 4;

/** The pair read from `anchor`'s side: the anchor first, and the confidences swapped to match. */
export function fromAnchorSide(p: ShopAnalyticsPair, anchor: string): ShopAnalyticsPair {
  if (p.first_id === anchor) return p;
  return { ...p, first: p.second, second: p.first, first_id: p.second_id, second_id: p.first_id,
           orders_with_first: p.orders_with_second, orders_with_second: p.orders_with_first,
           confidence: p.reverse_confidence, reverse_confidence: p.confidence };
}

/** The pairs to show: all of them, or those holding `anchor`, read from its side. */
export function pairsFor(section: ShopBasketSection, anchor: string): ShopAnalyticsPair[] {
  if (!anchor) return section.pairs;
  return section.pairs.filter((p) => p.first_id === anchor || p.second_id === anchor).map((p) => fromAnchorSide(p, anchor));
}

export function AnchorPicker({ section, anchor, onChange }: {
  section: ShopBasketSection; anchor: string; onChange: (anchor: string) => void;
}) {
  return (
    <select id="anchor-picker" className="search-input" style={{ paddingLeft: 12, width: "auto" }}
            value={anchor} onChange={(e) => onChange(e.target.value)}>
      <option value="">Every anchor</option>
      {section.anchors.map((a) => <option key={a.id} value={a.id}>{a.label}</option>)}
    </select>
  );
}

/**
 * Basket pairs as rules (ADR 0022's Basket Rules, ADR 0031's intervals):
 * lift and its interval, then confidence each way and support. A → B is
 * the share of A's orders that hold B; the two directions differ.
 */
export function BasketRuleTable({ section, pairs, filtered }: {
  section: ShopBasketSection; pairs: ShopAnalyticsPair[]; filtered: boolean;
}) {
  const together = pairs.filter((p) => p.lift > 1);
  const apart = pairs.filter((p) => p.lift < 1).sort((a, b) => a.lift - b.lift);
  const shown = filtered ? [...together, ...apart] : [...together.slice(0, TOGETHER_SHOWN), ...apart.slice(0, APART_SHOWN)];
  const effects = Object.values(section.design_effects);
  return (
    <>
      <div className="card-sub" style={{ marginBottom: 8 }}>
        {pairs.length} pairs clear the bar{filtered ? " for this anchor" : ""}
      </div>
      <div style={{ overflowX: "auto" }}>
        <table className="data-table" id="basket-rules">
          <thead>
            <tr><th>A + B</th><th>Lift</th><th title="Share of A's orders that hold B">A → B</th>
                <th title="Share of B's orders that hold A">B → A</th><th title="Share of all orders holding both">Support</th></tr>
          </thead>
          <tbody>
            {shown.map((p) => (
              <tr key={`${p.first_id}-${p.second_id}`}>
                <td>
                  {p.first} + {p.second}
                  <div className="card-sub" style={{ fontSize: 11 }}>{fmt(p.orders_with_both)} orders with both</div>
                </td>
                <td style={{ whiteSpace: "nowrap" }}>
                  <strong style={{ color: p.lift > 1 ? "var(--green)" : "var(--red)" }}>{p.lift.toFixed(2)}×</strong>
                  <span className="card-sub" style={{ fontSize: 11 }}> {p.interval_low.toFixed(2)}–{p.interval_high.toFixed(2)}</span>
                </td>
                <td>{pct(p.confidence)}</td>
                <td>{pct(p.reverse_confidence)}</td>
                <td>{pct(p.support)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!filtered && <More count={together.length - TOGETHER_SHOWN} what="pairs bought together (pick an anchor to see them)" />}
      {!filtered && <More count={apart.length - APART_SHOWN} what="pairs kept apart" />}
      <Threshold significance={section.significance}
                 designEffect={`clustering by customer (design effect ${Math.min(...effects).toFixed(1)}–${Math.max(...effects).toFixed(1)} by anchor)`} />
    </>
  );
}
