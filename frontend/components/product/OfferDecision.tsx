"use client";

import Link from "next/link";

import { fmtEur } from "@/lib/api";
import type { ProductView } from "@/lib/types";
import { BAND_LABEL, monthLabel, pct } from "./labels";

/**
 * What the Product view leads with: the discount band whose showings earn
 * the most (src/product_decision.py), its estimated effect on sales and
 * margin, next month's units and profit from the price model, and the
 * reasons from Aito's `$why`. Every number is an estimate, and says so.
 */
export default function OfferDecision({ view }: { view: ProductView }) {
  const { decision, discount, price_now: now, price_best: best } = view;
  const bestBand = discount.bands.find((b) => b.band === decision.best_band)!;
  const atList = decision.margins[0];
  const marginChange = decision.best.margin_per_100_eur / decision.current.margin_per_100_eur - 1;
  const slope = best ? (best.units - now.units) / (best.price_eur - now.price_eur) : null;

  return (
    <div className="card" style={{ borderTop: "3px solid var(--cta)", marginBottom: 20 }}>
      <div className="card-sub">The decision · estimates from Aito</div>
      <div className="page-title" style={{ fontSize: 22, margin: "4px 0 6px" }}>{headline(view)}</div>
      <div style={{ fontSize: 14, color: "var(--text-2)", marginBottom: 14 }}>
        {decision.action === "keep" && decision.best_band === "none"
          ? <>No discount earns more per showing: an offer would lift the chance it is bought when shown
              from {pct(atList.p_purchase)} to at most {pct(Math.max(...decision.margins.map((m) => m.p_purchase)))},
              not enough to pay for the lower price.</>
          : <>At {BAND_LABEL[decision.best_band].toLowerCase()}, Aito estimates a shopper shown it buys it{" "}
              <strong>{pct(decision.best.p_purchase)}</strong> of the time, against {pct(atList.p_purchase)} at
              list price (×{decision.expected_ratio.toFixed(2)}).</>}
      </div>

      <div className="kpi-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))" }}>
        <Tile label="Bought when shown"
              value={decision.best_band === decision.current_band
                ? pct(decision.best.p_purchase)
                : `${pct(decision.current.p_purchase)} → ${pct(decision.best.p_purchase)}`}
              sub={`now (${BAND_LABEL[decision.current_band].toLowerCase()}) → advised`} />
        <Tile label="Margin per 100 showings"
              value={decision.best_band === decision.current_band
                ? fmtEur(decision.best.margin_per_100_eur, 2)
                : `${fmtEur(decision.current.margin_per_100_eur, 2)} → ${fmtEur(decision.best.margin_per_100_eur, 2)}`}
              sub={decision.best_band === decision.current_band
                ? `at ${fmtEur(decision.best.price_eur, 2)}, cost ${fmtEur(view.product.unit_cost_eur, 2)}`
                : decision.current.margin_per_100_eur > 0
                  ? `${marginChange >= 0 ? "+" : ""}${(marginChange * 100).toFixed(0)} % · one unit per purchase`
                  : "one unit per purchase"} />
        {decision.breakeven_ratio !== null && (
          <Tile label="Sales needed to break even"
                value={`×${decision.breakeven_ratio.toFixed(2)}`}
                sub={`at ${fmtEur(decision.best.price_eur, 2)}; Aito expects ×${decision.expected_ratio.toFixed(2)}`} />
        )}
        <Tile label={`${monthLabel(view.forecast_month)}, price model`}
              value={best ? `${now.units.toFixed(1)} → ${best.units.toFixed(1)} units` : `${now.units.toFixed(1)} units`}
              sub={best
                ? `profit ${fmtEur(now.profit_eur, 2)} → ${fmtEur(best.profit_eur, 2)}`
                : `profit ${fmtEur(now.profit_eur, 2)} at ${fmtEur(now.price_eur, 2)}`} />
      </div>

      <div style={{ fontSize: 13, marginBottom: 8 }}>
        <strong>Why:</strong>{" "}
        <span style={{ fontFamily: "var(--mono)", fontSize: 12 }}>
          {pct(bestBand.base_p)} (all impressions)
          {bestBand.product_lift !== null && <> × {bestBand.product_lift.toFixed(2)} (this product)</>}
          {bestBand.band_lift !== null && <> × {bestBand.band_lift.toFixed(2)} ({BAND_LABEL[bestBand.band].toLowerCase()}, shop-wide)</>}
          {" "}× {bestBand.normaliser.toFixed(2)} (Aito&apos;s normaliser) = {pct(bestBand.p_purchase)}
        </span>
      </div>
      <div className="card-sub">
        Estimates. The discount band&apos;s lift is shop-wide: Aito learned it from every product&apos;s
        impressions, so it is the same for every product. Margin per showing assumes one unit per
        purchase and as many showings as now. The price model sees the price, not the offer label,
        and learns one price effect for all products
        {slope !== null && Number.isFinite(slope) && <> (here {Math.abs(slope).toFixed(1)} units per €)</>}:
        it shows what the lower price costs, not what the offer earns.{" "}
        <Link href="/evidence/model-checks/">How well? →</Link>
      </div>
    </div>
  );
}

function headline({ decision }: ProductView): string {
  const band = BAND_LABEL[decision.best_band].toLowerCase();
  switch (decision.action) {
    case "offer": return `Put it on offer at ${band}`;
    case "change": return `Change its offer to ${band}`;
    case "end_offer": return "End its offer: list price earns more per showing";
    case "keep": return decision.best_band === "none"
      ? "Keep it at list price"
      : `Keep its offer at ${band}`;
  }
}

function Tile({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="card kpi-card">
      <div className="kpi-label">{label}</div>
      <div className="kpi-val" style={{ fontSize: 16 }}>{value}</div>
      <div className="card-sub">{sub}</div>
    </div>
  );
}
