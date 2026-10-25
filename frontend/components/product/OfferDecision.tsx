"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import HelpPopover from "@/components/prediction/HelpPopover";
import { fmtEur } from "@/lib/api";
import type { BandMargin, DiscountBandEstimate, ProductView } from "@/lib/types";
import { BAND_LABEL, monthLabel, pct } from "./labels";

/**
 * The right of the Product view: what the offer is estimated to do. It leads with the advised
 * discount band (src/product_decision.py), or, when the owner previews a band on the left, with
 * that band against the one it has now. Four numbers, each with a ? that explains it, so the page
 * stays a few figures and the "why" is one click away. Every number is an estimate, and says so.
 */
export default function OfferDecision({ view, previewBand }: { view: ProductView; previewBand: string | null }) {
  const { decision, discount, price_now: now, price_best: best, product } = view;
  const current = decision.current;
  const target: BandMargin = previewBand ? decision.margins.find((m) => m.band === previewBand)! : decision.best;
  const targetBand = discount.bands.find((b) => b.band === target.band)!;
  const atList = decision.margins[0];
  const changing = target.band !== decision.current_band;
  const marginChange = current.margin_per_100_eur > 0 ? target.margin_per_100_eur / current.margin_per_100_eur - 1 : null;
  const marginPerUnit = target.price_eur - product.unit_cost_eur;
  const breakeven = target.band !== "none" && marginPerUnit > 0 ? (product.price_eur - product.unit_cost_eur) / marginPerUnit : null;
  const slope = best ? (best.units - now.units) / (best.price_eur - now.price_eur) : null;

  return (
    <div className="card" style={{ borderTop: "3px solid var(--cta)" }}>
      <div className="card-sub">{previewBand ? "Preview · nothing is saved" : "The decision"} · estimates from Aito</div>
      <div className="page-title" style={{ fontSize: 21, margin: "4px 0 6px" }}>
        {previewBand ? `If it were ${BAND_LABEL[target.band].toLowerCase()}` : headline(view)}
      </div>
      <div style={{ fontSize: 14, color: "var(--text-2)", marginBottom: 14 }}>
        {previewBand
          ? <>A shopper shown it would buy it <strong>{pct(target.p_purchase)}</strong> of the time, against {pct(current.p_purchase)} at {BAND_LABEL[decision.current_band].toLowerCase()}.
              {" "}Advised: {BAND_LABEL[decision.best_band].toLowerCase()} (margin per 100 showings {fmtEur(decision.best.margin_per_100_eur, 2)}).</>
          : decision.action === "keep" && decision.best_band === "none"
            ? <>No discount earns more per showing: an offer would lift the chance it is bought when shown from {pct(atList.p_purchase)} to
                at most {pct(Math.max(...decision.margins.map((m) => m.p_purchase)))}, not enough to pay for the lower price.</>
            : <>At {BAND_LABEL[decision.best_band].toLowerCase()}, a shopper shown it buys it <strong>{pct(decision.best.p_purchase)}</strong> of the
                time, against {pct(atList.p_purchase)} at list price (×{decision.expected_ratio.toFixed(2)}).</>}
      </div>

      <div className="kpi-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))" }}>
        <Tile label="Bought when shown"
              value={changing ? `${pct(current.p_purchase)} → ${pct(target.p_purchase)}` : pct(target.p_purchase)}
              sub={`now (${BAND_LABEL[decision.current_band].toLowerCase()}) → ${previewBand ? "previewed" : "advised"}`}
              help={<>
                <p style={{ margin: "0 0 8px" }}>
                  Aito&apos;s chance that a shopper shown this product buys it, with the offer set to the band
                  (<code>_predict purchased</code> on the shop&apos;s showings). The band&apos;s lift is learned across the whole shop, the same
                  for every product; this product&apos;s own lift is its own history.
                </p>
                <Chain b={targetBand} />
              </>} />
        <Tile label="Margin per 100 showings"
              value={changing ? `${fmtEur(current.margin_per_100_eur, 2)} → ${fmtEur(target.margin_per_100_eur, 2)}` : fmtEur(target.margin_per_100_eur, 2)}
              sub={changing && marginChange !== null
                ? `${marginChange >= 0 ? "+" : ""}${(marginChange * 100).toFixed(0)} % · at ${fmtEur(target.price_eur, 2)}`
                : `at ${fmtEur(target.price_eur, 2)}, cost ${fmtEur(product.unit_cost_eur, 2)}`}
              help={<p style={{ margin: 0 }}>
                100 × the chance it is bought when shown × (price − cost). It assumes one unit per purchase and as many showings as now,
                so it compares bands, it doesn&apos;t forecast revenue.
              </p>} />
        {breakeven !== null && (
          <Tile label="Sales needed to break even" value={`×${breakeven.toFixed(2)}`}
                sub={`at ${fmtEur(target.price_eur, 2)}; Aito expects ×${targetBand.vs_no_discount.toFixed(2)}`}
                help={<p style={{ margin: 0 }}>
                  How many times as many purchases the lower price needs to earn the same margin per showing as list price:
                  (list − cost) ÷ (price − cost). Compare it with what Aito expects: above it, the offer pays.
                </p>} />
        )}
        <Tile label={`${monthLabel(view.forecast_month)}, price model`}
              value={best ? `${now.units.toFixed(1)} → ${best.units.toFixed(1)} units` : `${now.units.toFixed(1)} units`}
              sub={best ? `profit ${fmtEur(now.profit_eur, 2)} → ${fmtEur(best.profit_eur, 2)} · at the advised price`
                        : `profit ${fmtEur(now.profit_eur, 2)} at ${fmtEur(now.price_eur, 2)}`}
              help={<p style={{ margin: 0 }}>
                Next month&apos;s units and profit from a regression on units sold and price (<code>_estimate units_sold</code>). It sees the
                price, not the offer label, and learns one price effect for all products
                {slope !== null && Number.isFinite(slope) && <> (here {Math.abs(slope).toFixed(1)} units per €)</>}: it shows
                what the lower price costs, not what the offer earns.
              </p>} />
      </div>

      <div className="card-sub" style={{ marginTop: 10 }}>
        Estimates; the band&apos;s lift is shop-wide. <Link href="/evidence/model-checks/">How well? →</Link>
      </div>
    </div>
  );
}

/** One band's `$why`, multiplied out: it equals the estimate (the backend checks that it does). */
function Chain({ b }: { b: DiscountBandEstimate }) {
  return (
    <div style={{ fontFamily: "var(--mono)", fontSize: 12 }}>
      {pct(b.base_p)} (all impressions)
      {b.product_lift !== null && <> × {b.product_lift.toFixed(2)} (this product)</>}
      {b.band_lift !== null && <> × {b.band_lift.toFixed(2)} ({BAND_LABEL[b.band].toLowerCase()}, shop-wide)</>}
      {" "}× {b.normaliser.toFixed(2)} (Aito&apos;s normaliser) = <strong>{pct(b.p_purchase)}</strong>
    </div>
  );
}

function headline({ decision }: ProductView): string {
  const band = BAND_LABEL[decision.best_band].toLowerCase();
  switch (decision.action) {
    case "offer": return `Put it on offer at ${band}`;
    case "change": return `Change its offer to ${band}`;
    case "end_offer": return "End its offer: list price earns more per showing";
    case "keep": return decision.best_band === "none" ? "Keep it at list price" : `Keep its offer at ${band}`;
  }
}

function Tile({ label, value, sub, help }: { label: string; value: string; sub: string; help: ReactNode }) {
  return (
    <div className="card kpi-card">
      <div className="kpi-label" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 6 }}>
        <span>{label}</span>
        <HelpPopover label={`What is "${label}"?`} title={label}>{help}</HelpPopover>
      </div>
      <div className="kpi-val" style={{ fontSize: 16 }}>{value}</div>
      <div className="card-sub">{sub}</div>
    </div>
  );
}
