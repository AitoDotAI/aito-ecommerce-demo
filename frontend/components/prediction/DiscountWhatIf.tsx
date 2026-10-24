"use client";

import { useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";
import type { DiscountBandEstimate, DiscountWhatIf as DiscountWhatIfResult } from "@/lib/types";

const BAND_LABEL: Record<string, string> = {
  "none": "No discount",
  "10-15": "10–15 % off",
  "15-20": "15–20 % off",
  "20+": "20 % or more off",
};

/**
 * Discount what-if (ADR 0032): the chance a shopper buys this product when
 * it is shown, at each discount band. One `_predict purchased` per band on
 * `impressions`, with the band set through `product_state`, so a band the
 * product never had is a what-if. Beside each estimate, what the data holds
 * for the product at that band.
 */
export default function DiscountWhatIf({
  sku,
  onQuery,
}: {
  sku: string;
  onQuery: (body: Record<string, unknown>) => void;
}) {
  const [result, setResult] = useState<DiscountWhatIfResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let current = true;
    setError(null);
    apiFetch<DiscountWhatIfResult>(`/api/price/discount-what-if?sku=${encodeURIComponent(sku)}`)
      .then((res) => { if (current) setResult(res); }, (e) => { if (current) setError(String(e)); });
    return () => { current = false; };
  }, [sku]);

  const shown = result && result.sku === sku ? result : null;
  // The row whose $why is spelled out below the table: the current band
  // until a row is clicked.
  const [picked, setPicked] = useState<string | null>(null);
  useEffect(() => { setPicked(null); }, [sku]);
  const pickBand = (band: string) => {
    if (!shown) return;
    setPicked(band);
    const body = shown.last_query.body as { where: Record<string, unknown> };
    onQuery({ ...body, where: { ...body.where, "product_state.discount_band": band } });
  };
  const maxP = shown ? Math.max(...shown.bands.map((b) => b.p_purchase)) : 1;
  const chainBand = shown?.bands.find((b) => (picked ? b.band === picked : b.current)) ?? null;

  return (
    <div className="card" style={{ marginBottom: 20 }}>
      <div className="card-sub" style={{ marginBottom: 6 }}>
        Discount what-if · `_predict purchased` on impressions, per discount band · click a row for its $why and query
      </div>
      <div className="page-title" style={{ fontSize: 17, margin: "4px 0 12px" }}>
        If it were on offer: the chance a shopper buys it when it&apos;s shown
      </div>
      {error && <div className="card-sub" style={{ color: "var(--red)" }}>Couldn&apos;t predict: {error}</div>}
      {!error && !shown && <div style={{ height: 180, background: "var(--border-light)", borderRadius: 4 }} />}
      {!error && shown && (
        <>
          <div style={{ overflowX: "auto" }}>
            <table className="recent-table" style={{ width: "100%", fontSize: 12.5 }}>
              <thead>
                <tr>
                  <th style={{ textAlign: "left" }}>Discount</th>
                  <th style={{ textAlign: "left" }}>Bought when shown</th>
                  <th style={{ textAlign: "right" }}>vs. no discount</th>
                  <th style={{ textAlign: "right" }}>Band&apos;s lift</th>
                  <th style={{ textAlign: "right" }}>Product&apos;s lift</th>
                  <th style={{ textAlign: "right" }}>In the data</th>
                </tr>
              </thead>
              <tbody>
                {shown.bands.map((b) => (
                  <BandRow key={b.band} b={b} maxP={maxP} month={shown.month} onClick={() => pickBand(b.band)} />
                ))}
              </tbody>
            </table>
          </div>
          {chainBand && <Chain b={chainBand} />}
          {shown.bands.some((b) => b.calibrated) && (
            <div className="card-sub" style={{ marginTop: 6 }}>
              Few shoppers buy this product, and Aito holds its estimate at a
              floor (a <code>calibration</code> factor in <code>$why</code>): the
              band&apos;s lift is listed, but moves the estimate little or not at all.
            </div>
          )}
          <div className="card-sub" style={{ marginTop: 6 }}>
            Each estimate is Aito&apos;s, learned from all impressions: the
            band&apos;s lift is the same for every product. Where Aito leaves the
            product&apos;s lift out of <code>$why</code>, the estimate is the
            band&apos;s, not this product&apos;s. &ldquo;In the data&rdquo; is this
            product&apos;s own impressions at the band.
          </div>
        </>
      )}
    </div>
  );
}

function BandRow({ b, maxP, month, onClick }: {
  b: DiscountBandEstimate; maxP: number; month: string; onClick: () => void;
}) {
  return (
    <tr onClick={onClick} style={{
      cursor: "pointer",
      background: b.current ? "rgba(245,166,35,0.12)" : undefined,
      borderLeft: b.current ? "3px solid var(--cta)" : "3px solid transparent",
    }}>
      <td>
        <span style={{ fontWeight: 700 }}>{BAND_LABEL[b.band] ?? b.band}</span>
        {b.current && (
          <span className="pill" style={{
            marginLeft: 8, background: "var(--cta-bg)", color: "var(--cta)",
            fontSize: 10.5, fontWeight: 700, padding: "1px 6px", borderRadius: 6,
          }}>
            now · {month}
          </span>
        )}
      </td>
      <td>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{ flex: 1, minWidth: 60, maxWidth: 160, height: 8, background: "var(--border-light)", borderRadius: 4 }}>
            <div style={{ width: `${(b.p_purchase / maxP) * 100}%`, height: "100%", background: "var(--cta)", borderRadius: 4 }} />
          </div>
          <strong style={{ fontFamily: "var(--mono)" }}>{(b.p_purchase * 100).toFixed(1)} %</strong>
        </div>
      </td>
      <td style={{ textAlign: "right", fontFamily: "var(--mono)" }}>
        {b.band === "none" ? "—" : `×${b.vs_no_discount.toFixed(2)}`}
      </td>
      <td style={{ textAlign: "right", fontFamily: "var(--mono)" }}
          title={b.band_lift === null ? "Aito leaves the band out of $why: every impression of this product was at this band" : undefined}>
        {b.band_lift === null ? "not in $why" : `×${b.band_lift.toFixed(2)}`}
      </td>
      <td style={{ textAlign: "right", fontFamily: "var(--mono)" }}>
        {b.product_lift === null ? "not in $why" : `×${b.product_lift.toFixed(2)}`}
      </td>
      <td style={{ textAlign: "right", fontSize: 11.5, color: "var(--text-muted)" }}>
        {b.shown === 0 ? "never shown at this band" : `${b.purchased} bought of ${b.shown} shown`}
      </td>
    </tr>
  );
}

// One band's $why, multiplied out: it equals the estimate (the backend
// checks that it does).
function Chain({ b }: { b: DiscountBandEstimate }) {
  const parts = [
    `${(b.base_p * 100).toFixed(2)} % (all impressions)`,
    ...(b.product_lift === null ? [] : [`${b.product_lift.toFixed(3)} (this product)`]),
    ...(b.band_lift === null ? [] : [`${b.band_lift.toFixed(3)} (${BAND_LABEL[b.band].toLowerCase()})`]),
    `${b.normaliser.toFixed(3)} (Aito's normaliser)`,
  ];
  return (
    <div style={{ marginTop: 10, fontFamily: "var(--mono)", fontSize: 12, color: "var(--text-2)" }}>
      {BAND_LABEL[b.band]}{b.current ? " (now)" : ""}: {parts.join(" × ")} = <strong>{(b.p_purchase * 100).toFixed(2)} %</strong>
    </div>
  );
}
