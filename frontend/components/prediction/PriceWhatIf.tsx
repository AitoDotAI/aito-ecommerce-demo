"use client";

import { useEffect, useState } from "react";

import { apiFetch, fmtEur } from "@/lib/api";
import type { PriceDetail, PriceWhatIf as PriceWhatIfResult } from "@/lib/types";

/**
 * Price what-if (ADR 0029): pick a price, see next month's units, revenue
 * and profit, and the factors behind the estimate. Aito's regression
 * `_estimate` gives a base (an average month) times one factor per fact
 * about the product, so the rows multiply out to the estimate exactly.
 */
export default function PriceWhatIf({
  detail,
  price,
  onPrice,
  onQuery,
}: {
  detail: PriceDetail;
  /** The price asked about, from the URL; the curve's centre when null. */
  price: number | null;
  onPrice: (priceEur: number) => void;
  onQuery: (body: Record<string, unknown>) => void;
}) {
  const centre = detail.curve.find((c) => c.adjustment_pct === 0)?.price_eur ?? detail.mean_price_eur;
  const asked = price ?? centre;
  // The slider spans the curve, widened to the price asked about when a
  // link names one outside it.
  const prices = [...detail.curve.map((c) => c.price_eur), asked];
  const min = Math.min(...prices);
  const max = Math.max(...prices);

  // The slider moves freely; the price is committed (URL, request) once it
  // rests, so a drag is one history step and one `_estimate`.
  const [draft, setDraft] = useState(asked);
  useEffect(() => setDraft(asked), [asked]);
  useEffect(() => {
    if (draft === asked) return;
    const timer = setTimeout(() => onPrice(draft), 300);
    return () => clearTimeout(timer);
  }, [draft, asked, onPrice]);

  const [result, setResult] = useState<PriceWhatIfResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let current = true;
    setError(null);
    apiFetch<PriceWhatIfResult>(
      `/api/price/what-if?sku=${encodeURIComponent(detail.sku)}&price=${asked.toFixed(2)}`,
    ).then((res) => {
      if (!current) return;
      setResult(res);
      onQuery(res.last_query.body);
    }, (e) => { if (current) setError(String(e)); });
    return () => { current = false; };
  }, [detail.sku, asked, onQuery]);

  const shown = result && result.sku === detail.sku ? result : null;

  return (
    <div className="card" style={{ marginBottom: 20 }}>
      <div className="card-sub" style={{ marginBottom: 6 }}>
        What if · `_estimate units_sold` with the regression model · click a curve point or drag
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", marginBottom: 14 }}>
        <label htmlFor="what-if-price" style={{ fontWeight: 600 }}>Price</label>
        <input
          id="what-if-price" type="range" min={min} max={max} step={0.01} value={draft}
          onChange={(e) => setDraft(Number(e.target.value))} style={{ flex: 1, minWidth: 180 }}
        />
        <input
          aria-label="Price in euros" type="number" min={0.01} step={0.01} value={draft.toFixed(2)}
          onChange={(e) => { const v = Number(e.target.value); if (v > 0) setDraft(v); }}
          className="search-input" style={{ width: 96, paddingLeft: 8 }}
        />
      </div>

      {error && <div className="card-sub" style={{ color: "var(--red)" }}>Couldn&apos;t estimate: {error}</div>}
      {!error && !shown && <div style={{ height: 160, background: "var(--border-light)", borderRadius: 4 }} />}
      {!error && shown && (
        <div className="two-col">
          <div>
            <Kpi label="Units next month" value={shown.units.toFixed(1)} />
            <Kpi label="Revenue" value={fmtEur(shown.revenue_eur, 2)} />
            <Kpi label={`Profit (cost ${fmtEur(shown.cost_eur, 2)})`} value={fmtEur(shown.profit_eur, 2)} />
          </div>
          <Waterfall result={shown} />
        </div>
      )}
    </div>
  );
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid var(--border-light)" }}>
      <span style={{ color: "var(--text-muted)", fontSize: 13 }}>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

// Base × each factor, with the running total, ending at the estimate.
function Waterfall({ result }: { result: PriceWhatIfResult }) {
  let running = result.base_units;
  return (
    <div style={{ fontSize: 13 }}>
      <Row label="An average month" change="" total={running} />
      {result.factors.map((f) => {
        running *= f.multiplier;
        const pct = (f.multiplier - 1) * 100;
        return (
          <Row
            key={f.field}
            label={f.label}
            change={`${pct >= 0 ? "+" : "−"}${Math.abs(pct).toFixed(1)} %`}
            color={pct >= 0 ? "var(--green)" : "var(--red)"}
            total={running}
          />
        );
      })}
      <Row label="Estimate" change="" total={result.units} strong />
    </div>
  );
}

function Row({ label, change, total, color, strong }: {
  label: string; change: string; total: number; color?: string; strong?: boolean;
}) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 72px 64px", gap: 8, padding: "4px 0", fontWeight: strong ? 700 : 400 }}>
      <span>{label}</span>
      <span style={{ textAlign: "right", color }}>{change}</span>
      <span style={{ textAlign: "right", fontFamily: "var(--mono)" }}>{total.toFixed(1)}</span>
    </div>
  );
}
