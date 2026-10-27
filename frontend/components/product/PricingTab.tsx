"use client";

import { useEffect, useState } from "react";
import {
  CartesianGrid, ComposedChart, Line, ReferenceArea, ReferenceDot, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis,
} from "recharts";

import HelpPopover from "@/components/prediction/HelpPopover";
import { ApiError, apiFetch, fmtEur } from "@/lib/api";
import type { PricePoint, ProductPricing, ProductView } from "@/lib/types";
import { monthLabel, shortMonth } from "./labels";

type Measure = "units" | "profit";

/**
 * Product › Pricing (ADR 0050): type a list price and see the units and profit it gives, next to the
 * product's own months. Units come from `_estimate units_index` at the price, times the product's mean units
 * before the month. Beyond the prices the product has sold at, the page says "no data here" and gives no
 * number, and the best price is picked only among the prices it has data for.
 * Backend: src/product_pricing.py.
 */
export default function PricingTab({ view, listPrice, onListPrice, onQuery }: {
  view: ProductView;
  /** The list price asked about, from the URL; the month's own when null. */
  listPrice: number | null;
  onListPrice: (eur: number | null) => void;
  onQuery: (body: Record<string, unknown>) => void;
}) {
  const sku = view.product.sku, month = view.month;
  const [data, setData] = useState<ProductPricing | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [measure, setMeasure] = useState<Measure>("profit");
  const [typed, setTyped] = useState("");

  useEffect(() => {
    let current = true;
    setError(null);
    const query = new URLSearchParams({ sku, month });
    if (listPrice !== null) query.set("list_price", String(listPrice));
    apiFetch<ProductPricing>(`/api/product/pricing?${query}`).then((res) => {
      if (!current) return;
      setData(res);
      onQuery(res.last_query.body);
    }, (e) => { if (current) setError(e instanceof ApiError ? e.serverMessage ?? e.message : String(e)); });
    return () => { current = false; };
  }, [sku, month, listPrice, onQuery]);
  useEffect(() => { setTyped(listPrice !== null ? listPrice.toFixed(2) : ""); }, [listPrice, sku]);

  if (error) return <div className="card" style={{ color: "var(--red)" }}>Couldn&apos;t estimate the prices: {error}</div>;
  if (!data) return <div className="card" aria-busy="true" style={{ height: 420, background: "var(--border-light)" }} />;

  const commit = () => {
    const eur = Number(typed);
    if (typed.trim() === "") onListPrice(null);
    else if (Number.isFinite(eur) && eur > 0) onListPrice(eur);
    else setTyped(listPrice !== null ? listPrice.toFixed(2) : "");
  };
  const shown = data.asked ?? data.now;
  const value = (p: PricePoint) => (measure === "units" ? p.units : p.profit_eur);
  const answered = data.curve.filter((p) => p.in_range);
  const own = data.own_months.map((m) => {
    const price = m.price_index * data.reference_list_eur;
    return { x: price, y: measure === "units" ? m.units : m.units * (price - data.unit_cost_eur), month: m.month };
  });
  const line = answered.map((p) => ({ x: p.price_eur, y: value(p) }));
  const xs = [...data.curve.map((p) => p.price_eur), shown.price_eur];
  const triedLow = data.tried_from * data.reference_list_eur, triedHigh = data.tried_to * data.reference_list_eur;

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 380px), 1fr))", gap: 20, alignItems: "start" }}>
      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center" }}>
          <div className="card-title" style={{ margin: 0 }}>List price · {monthLabel(month)}</div>
          <HelpPopover label="How is this estimated?" title="How the prices are estimated">
            <p style={{ margin: "0 0 8px" }}>
              For each price Aito estimates <code>units_index</code>: the units the product sells compared with its own
              earlier months (1.0 is an average month), from the months the shop sold it at about that price. The units
              shown are that index times the {data.mean_units === null ? "product's mean units (it sold nothing before this month)" : <>product&apos;s mean of {data.mean_units.toFixed(1)} units a month before {monthLabel(month)}</>}.
            </p>
            <p style={{ margin: "0 0 8px" }}>
              The price index is the price paid against the product&apos;s first list price ({fmtEur(data.reference_list_eur, 2)}).
              The month&apos;s offer ({data.offer_pct ? `${data.offer_pct.toFixed(0)} % off` : "none"}) comes off the list price you type.
            </p>
            <p style={{ margin: 0, color: "var(--text-muted)" }}>
              The product has sold at {fmtEur(triedLow, 2)}–{fmtEur(triedHigh, 2)}. Prices more than 5 % beyond that
              have no data behind them, so they get no estimate and cannot be the best price.
            </p>
          </HelpPopover>
        </div>
        <label style={{ display: "flex", gap: 8, alignItems: "center", margin: "12px 0 4px" }}>
          <span style={{ fontSize: 13, fontWeight: 600 }}>List price €</span>
          <input className="search-input" style={{ width: 110, paddingLeft: 8 }} inputMode="decimal" value={typed}
                 placeholder={data.list_price_eur.toFixed(2)} aria-label="List price in euros"
                 onChange={(e) => setTyped(e.target.value)} onBlur={commit}
                 onKeyDown={(e) => { if (e.key === "Enter") commit(); }} />
          {listPrice !== null && <button type="button" className="btn btn-ghost" onClick={() => onListPrice(null)}>Reset</button>}
        </label>
        <div className="card-sub" style={{ marginBottom: 10 }}>
          now {fmtEur(data.list_price_eur, 2)} · cost {fmtEur(data.unit_cost_eur, 2)}
          {data.offer_pct > 0 && <> · offer {data.offer_pct.toFixed(0)} % off, so shoppers pay {fmtEur(shown.price_eur, 2)}</>}
        </div>

        {data.mean_units === null ? (
          <div className="card-sub">This product sold nothing before {monthLabel(month)}, so there is no mean to scale an index by.</div>
        ) : !shown.in_range ? (
          <div role="status" style={{ padding: 10, background: "var(--orange-bg, var(--border-light))", borderRadius: 6, fontSize: 13 }}>
            <strong>No data here.</strong> {fmtEur(shown.price_eur, 2)} is outside what this product has sold at
            ({fmtEur(triedLow, 2)}–{fmtEur(triedHigh, 2)}), so there is no estimate.
          </div>
        ) : (
          <Summary asked={shown} now={data.now} changed={data.asked !== null} />
        )}
        {data.best && (
          <div className="card-sub" style={{ marginTop: 10 }}>
            Most profit among the prices it has data for: <strong>{fmtEur(data.best.list_price_eur, 2)}</strong> list,
            {" "}{fmtEur(data.best.profit_eur, 0)} a month
            {data.best.list_price_index === data.now.list_price_index ? <> (today&apos;s price)</>
              : <> against {fmtEur(data.now.profit_eur, 0)} at today&apos;s</>}.
          </div>
        )}
      </div>

      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
          <div className="card-sub">{measure === "units" ? "Units" : "Profit"} by price paid · {data.own_months.length} months as dots</div>
          <div role="group" aria-label="Measure" style={{ display: "flex", gap: 6 }}>
            {(["profit", "units"] as const).map((m) => (
              <button key={m} type="button" aria-pressed={measure === m} className={`btn${measure === m ? "" : " btn-ghost"}`}
                      onClick={() => setMeasure(m)}>{m === "units" ? "Units" : "Profit €"}</button>
            ))}
          </div>
        </div>
        <ResponsiveContainer width="100%" height={340}>
          <ComposedChart margin={{ top: 12, right: 16, bottom: 28, left: 40 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-light)" />
            <XAxis type="number" dataKey="x" domain={[Math.min(...xs) * 0.97, Math.max(...xs) * 1.03]} tickFormatter={(v) => `€${Number(v).toFixed(1)}`}
                   tick={{ fontSize: 11, fill: "var(--text-muted)" }} label={{ value: "Price paid", position: "insideBottom", offset: -14, style: { fontSize: 12, fill: "var(--text-2)" } }} />
            <YAxis type="number" dataKey="y" domain={["auto", "auto"]} tick={{ fontSize: 11, fill: "var(--text-muted)" }}
                   tickFormatter={(v) => (measure === "units" ? String(v) : `€${v}`)} />
            <Tooltip formatter={(v) => (measure === "units" ? `${Number(v).toFixed(1)} units` : fmtEur(Number(v), 0))}
                     labelFormatter={(v) => fmtEur(Number(v), 2)} />
            <ReferenceArea x1={Math.min(...xs) * 0.97} x2={triedLow * 0.95} fill="var(--border-light)" fillOpacity={0.7}
                           label={{ value: "no data", fontSize: 11, fill: "var(--text-muted)" }} />
            <ReferenceArea x1={triedHigh * 1.05} x2={Math.max(...xs) * 1.03} fill="var(--border-light)" fillOpacity={0.7}
                           label={{ value: "no data", fontSize: 11, fill: "var(--text-muted)" }} />
            <Scatter data={own} dataKey="y" fill="var(--text-muted)" name="A month" />
            <Line data={line} dataKey="y" stroke="var(--cta)" strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} name="Aito's estimate" />
            <ReferenceDot x={data.now.price_eur} y={value(data.now)} r={6} fill="var(--accent)" stroke="white" ifOverflow="extendDomain" />
            {data.asked && data.asked.in_range && (
              <ReferenceDot x={data.asked.price_eur} y={value(data.asked)} r={7} fill="var(--cta)" stroke="white" ifOverflow="extendDomain" />
            )}
            {data.best && <ReferenceDot x={data.best.price_eur} y={value(data.best)} r={5} fill="none" stroke="var(--green)" strokeWidth={2} ifOverflow="extendDomain" />}
          </ComposedChart>
        </ResponsiveContainer>
        <div className="card-sub">
          Green ring: most profit with data. Orange: your price. Teal dot: today&apos;s. Grey: months it sold.
          Grey areas: no data.
          {data.own_months.length > 0 && <> Latest month {shortMonth(data.own_months[data.own_months.length - 1].month)}.</>}
        </div>
      </div>
    </div>
  );
}

function Summary({ asked, now, changed }: { asked: PricePoint; now: PricePoint; changed: boolean }) {
  const delta = (a: number, b: number) => (b ? `${a >= b ? "+" : "−"}${Math.abs((a / b - 1) * 100).toFixed(0)} %` : "");
  return (
    <div className="kpi-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))" }}>
      {[
        { label: "Units", value: asked.units.toFixed(1), was: now.units, now: asked.units },
        { label: "Revenue", value: fmtEur(asked.revenue_eur, 0), was: now.revenue_eur, now: asked.revenue_eur },
        { label: "Profit", value: fmtEur(asked.profit_eur, 0), was: now.profit_eur, now: asked.profit_eur },
      ].map((k) => (
        <div key={k.label} className="card kpi-card">
          <div className="kpi-label">{k.label} a month</div>
          <div className="kpi-val" style={{ fontSize: 18 }}>{k.value}</div>
          {changed && <div className="card-sub">{delta(k.now, k.was)} against today</div>}
        </div>
      ))}
    </div>
  );
}
