"use client";

import { useEffect, useState } from "react";

import { apiFetch, fmtEur } from "@/lib/api";
import type { PriceCurve, ProductView } from "@/lib/types";
import DiscountWhatIf from "./DiscountWhatIf";
import PriceScatterChart from "./PriceScatterChart";
import PriceWhatIf from "./PriceWhatIf";
import { monthLabel } from "./labels";

/**
 * Product › What if: the two levers side by side. The price (ADR 0029):
 * a demand and profit curve from `_estimate units_sold` at seven prices,
 * and the units waterfall at a price the user picks. The discount
 * (ADR 0032): the chance it is bought when shown, per band.
 */
export default function ProductWhatIf({ view, price, onPrice, onQuery }: {
  view: ProductView;
  /** The price asked about, from the URL; today's price when null. */
  price: number | null;
  onPrice: (priceEur: number) => void;
  onQuery: (body: Record<string, unknown>) => void;
}) {
  const sku = view.product.sku;
  const [curve, setCurve] = useState<PriceCurve | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let current = true;
    setCurve(null);
    setError(null);
    apiFetch<PriceCurve>(`/api/product/price-curve?sku=${encodeURIComponent(sku)}`)
      .then((res) => { if (current) setCurve(res); }, (e) => { if (current) setError(String(e)); });
    return () => { current = false; };
  }, [sku]);

  const ends = curve ? [curve.curve[0], curve.curve[curve.curve.length - 1]] : null;
  const slope = ends ? (ends[1].units_sold - ends[0].units_sold) / (ends[1].price_eur - ends[0].price_eur) : null;

  return (
    // Side by side where there is room for both tables, stacked otherwise.
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 540px), 1fr))",
                  gap: 20, alignItems: "start" }}>
      <div>
        <div className="card" style={{ marginBottom: 20 }}>
          <div className="card-sub" style={{ marginBottom: 6 }}>
            Price what-if · {monthLabel(view.forecast_month)} · `_estimate units_sold` at seven prices
          </div>
          <div className="page-title" style={{ fontSize: 17, margin: "4px 0 8px" }}>
            Units and profit next month, by price
          </div>
          <div className="card-sub" style={{ marginBottom: 10, color: "var(--text-2)" }}>
            <strong>The price effect is shop-wide.</strong>{" "}Aito&apos;s regression learns one price effect
            from all products&apos; months, so this curve&apos;s slope
            {slope !== null && <> ({slope.toFixed(1)} units per €)</>} is{" "}
            {view.price_now.form === "add" ? "the same units per € for every product" : "the same share of units per € for every product"},
            not this product&apos;s own price sensitivity. Its own months are the dots.
          </div>
          {error && <div className="card-sub" style={{ color: "var(--red)" }}>Couldn&apos;t estimate the curve: {error}</div>}
          {!error && !curve && <div aria-busy="true" style={{ height: 360, background: "var(--border-light)", borderRadius: 4 }} />}
          {curve && (
            <>
              <div className="card-sub">
                list {fmtEur(curve.list_price_eur, 2)} · cost {fmtEur(curve.unit_cost_eur, 2)} ·
                average selling price {fmtEur(curve.mean_price_eur, 2)} · {curve.historical.length} months
              </div>
              <PriceScatterChart detail={curve} onPickPrice={onPrice} />
            </>
          )}
        </div>
        {curve && (
          <PriceWhatIf detail={curve} price={price ?? view.price_now.price_eur} known={view.price_now}
                       onPrice={onPrice} onQuery={onQuery} />
        )}
      </div>
      <div>
        <DiscountWhatIf result={view.discount} margins={view.decision.margins} onQuery={onQuery} />
      </div>
    </div>
  );
}
