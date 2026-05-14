"use client";

import { useState } from "react";
import {
  ComposedChart,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  Scatter,
  Line,
  ResponsiveContainer,
} from "recharts";

import type { PriceDetail } from "@/lib/types";


/**
 * Price ↔ Demand / Profit scatter — mirrors aito-demo's
 * `PricingPage` scatter plot. Historical (price, units) pairs as
 * a light scatter, Aito's `_estimate units_sold` curve at +/-15 %
 * price adjustments as an orange line, current list price as the
 * highlighted star.
 *
 * Toggle the Y-axis between Demand (units) and Profit (€) — the
 * curve and points update in place. Profit = (price - unit_cost)
 * × units; max-profit point on the curve gets emphasised.
 */
export default function PriceScatterChart({ detail }: { detail: PriceDetail }) {
  const [yMode, setYMode] = useState<"demand" | "profit">("demand");

  const historical = detail.historical.map((h) => ({
    x: h.price_eur,
    y: yMode === "demand" ? h.units_sold : h.profit_eur,
    price: h.price_eur,
    units: h.units_sold,
    profit: h.profit_eur,
    month: h.month,
  }));

  const curve = [...detail.curve]
    .sort((a, b) => a.price_eur - b.price_eur)
    .map((c) => ({
      x: c.price_eur,
      y: yMode === "demand" ? c.units_sold : c.profit_eur,
      price: c.price_eur,
      units: c.units_sold,
      profit: c.profit_eur,
      adj: c.adjustment_pct,
    }));

  // Current list-price point — visually anchor the "this is where
  // we are today" position. Use the central (0%) curve point so
  // demand/profit come from Aito's estimate at the SKU's mean
  // realised price.
  const central = detail.curve.find((c) => c.adjustment_pct === 0);
  const currentPoint = central
    ? [{
        x: central.price_eur,
        y: yMode === "demand" ? central.units_sold : central.profit_eur,
        price: central.price_eur,
        units: central.units_sold,
        profit: central.profit_eur,
        adj: 0,
      }]
    : [];

  // Max-profit point on the curve (only highlighted in profit mode).
  const maxProfit = detail.curve.length
    ? [...detail.curve].sort((a, b) => b.profit_eur - a.profit_eur)[0]
    : null;
  const maxProfitPoint =
    yMode === "profit" && maxProfit
      ? [{
          x: maxProfit.price_eur,
          y: maxProfit.profit_eur,
          price: maxProfit.price_eur,
          units: maxProfit.units_sold,
          profit: maxProfit.profit_eur,
          adj: maxProfit.adjustment_pct,
        }]
      : [];

  return (
    <div>
      {/* Header: SKU name + Y-mode toggle */}
      <div style={{
        display: "flex", justifyContent: "space-between",
        alignItems: "baseline", marginBottom: 4,
      }}>
        <div>
          <div style={{ fontWeight: 700, fontSize: 16 }}>{detail.name}</div>
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>
            list €{detail.list_price_eur.toFixed(2)} · cost €{detail.unit_cost_eur.toFixed(2)}
            {" · "}{detail.historical.length} historical months
          </div>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          <button
            type="button"
            onClick={() => setYMode("demand")}
            style={toggleBtnStyle(yMode === "demand")}
          >
            Demand
          </button>
          <button
            type="button"
            onClick={() => setYMode("profit")}
            style={toggleBtnStyle(yMode === "profit")}
          >
            Profit €
          </button>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={360}>
        <ComposedChart margin={{ top: 12, right: 24, bottom: 32, left: 48 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border-light)" />
          <XAxis
            type="number"
            dataKey="x"
            name="Price"
            domain={["auto", "auto"]}
            tickFormatter={(v) => `€${v}`}
            label={{
              value: "Price (€)",
              position: "insideBottom",
              offset: -10,
              style: { fontSize: 12, fontWeight: 600, fill: "var(--text-2)" },
            }}
            tick={{ fontSize: 11, fill: "var(--text-muted)" }}
            stroke="var(--text-muted)"
          />
          <YAxis
            type="number"
            dataKey="y"
            domain={["auto", "auto"]}
            tickFormatter={(v) =>
              yMode === "demand" ? String(v) : `€${v}`
            }
            label={{
              value: yMode === "demand" ? "Units sold" : "Profit (€)",
              angle: -90,
              position: "insideLeft",
              offset: -36,
              style: { fontSize: 12, fontWeight: 600, fill: "var(--text-2)" },
            }}
            tick={{ fontSize: 11, fill: "var(--text-muted)" }}
            stroke="var(--text-muted)"
          />
          <Tooltip content={<PriceTooltip yMode={yMode} />} cursor={{ strokeDasharray: "3 3" }} />
          <Legend
            verticalAlign="top"
            height={32}
            iconType="circle"
            wrapperStyle={{ fontSize: 12, fontWeight: 500 }}
          />

          {/* Historical scatter (light blue, small) */}
          <Scatter
            name="Historical months"
            data={historical}
            fill="#8dd1e1"
            opacity={0.65}
          />

          {/* Aito curve (orange line + dots) */}
          {curve.length > 0 && (
            <Line
              name={yMode === "demand" ? "Aito demand curve" : "Aito profit curve"}
              data={curve}
              type="monotone"
              dataKey="y"
              stroke="var(--cta)"
              strokeWidth={2.5}
              dot={{ fill: "var(--cta)", r: 4 }}
              isAnimationActive={false}
            />
          )}

          {/* Max-profit (in profit mode) — yellow ring */}
          {maxProfitPoint.length > 0 && (
            <Scatter
              name={`Max profit @ ${maxProfit?.adjustment_pct ?? 0 > 0 ? "+" : ""}${maxProfit?.adjustment_pct ?? 0}%`}
              data={maxProfitPoint}
              fill="#FFD23F"
              shape="circle"
              r={9}
            />
          )}

          {/* Current list price — star */}
          {currentPoint.length > 0 && (
            <Scatter
              name="Current list price"
              data={currentPoint}
              fill="var(--cta)"
              shape="star"
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}


function PriceTooltip({
  active, payload, yMode,
}: {
  active?: boolean;
  payload?: Array<{ payload: { price: number; units: number; profit: number; month?: string; adj?: number } }>;
  yMode: "demand" | "profit";
}) {
  if (!active || !payload || payload.length === 0) return null;
  const p = payload[0].payload;
  return (
    <div style={{
      background: "var(--white)",
      border: "1px solid var(--cta)",
      borderRadius: 6,
      padding: "8px 10px",
      fontSize: 12,
      lineHeight: 1.5,
      boxShadow: "0 4px 12px rgba(0,0,0,0.15)",
    }}>
      <div style={{ fontWeight: 700 }}>€{p.price.toFixed(2)} / unit</div>
      <div>Units: {typeof p.units === "number" ? p.units.toFixed(2) : "—"}</div>
      <div>Profit: €{typeof p.profit === "number" ? p.profit.toFixed(2) : "—"}</div>
      {p.month && (
        <div style={{ color: "var(--text-muted)", marginTop: 2 }}>{p.month}</div>
      )}
      {p.adj !== undefined && p.adj !== null && (
        <div style={{ color: "var(--text-muted)", marginTop: 2 }}>
          adjustment: {p.adj > 0 ? "+" : ""}{p.adj}%
        </div>
      )}
    </div>
  );
}


function toggleBtnStyle(active: boolean): React.CSSProperties {
  return {
    fontSize: 12,
    fontWeight: 600,
    padding: "4px 10px",
    border: "1px solid var(--cta)",
    borderRadius: 6,
    background: active ? "var(--cta)" : "transparent",
    color: active ? "white" : "var(--cta)",
    cursor: "pointer",
  };
}
