"use client";

import { useState } from "react";

import { kpiSpec } from "@/lib/customer-kpis";
import type { KpiId, SegmentView } from "@/lib/customer-profiles";

const WIDTH = 520;
const HEIGHT = 140;
const WORSE_THAN_ALL_BY = 0.03;   // ratio KPIs: and this much (3 points of change) worse than everyone's change

const PRESETS = [3, 6, 12];

/**
 * The top right: the chosen figure over the shop's months for the segment, and whether it is in decline against everyone.
 * Drag across the months, or pick a preset, to set a period against the rest of the history (ADR 0055).
 */
export default function SegmentTrend({ view, kpi, from, to, onPeriod }: {
  view: SegmentView; kpi: KpiId; from: string; to: string; onPeriod: (from: string, to: string) => void;
}) {
  const [drag, setDrag] = useState<{ anchor: number; at: number } | null>(null);
  if (!view.trend) return null;
  const spec = kpiSpec(kpi);
  const mine = view.trend.selected;
  const everyone = view.trend.all;
  const series: (number | null)[] = mine[kpi];
  const known = series.filter((v): v is number => v !== null);
  const level = known.reduce((a, b) => a + b, 0) / (known.length || 1) || 1;
  const everyoneSeries: (number | null)[] = everyone[kpi];
  const everyoneKnown = everyoneSeries.filter((v): v is number => v !== null);
  const everyoneLevel = everyoneKnown.reduce((a, b) => a + b, 0) / (everyoneKnown.length || 1) || 1;
  // Everyone, scaled to the segment's average level, so the two curves compare in shape and not in size.
  const scaled = everyoneSeries.map((v) => (v === null ? null : (v / everyoneLevel) * level));
  const values = [...known, ...scaled.filter((v): v is number => v !== null)];
  const low = Math.min(0, ...values);
  const top = Math.max(...values, 1e-9);
  const x = (i: number) => (i / Math.max(1, series.length - 1)) * (WIDTH - 20) + 10;
  const months = mine.months;
  const monthAt = (event: React.PointerEvent<SVGSVGElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    const position = ((event.clientX - box.left) / box.width) * WIDTH;
    return Math.min(months.length - 1, Math.max(0, Math.round(((position - 10) / (WIDTH - 20)) * (months.length - 1))));
  };
  const chosen = drag ? [Math.min(drag.anchor, drag.at), Math.max(drag.anchor, drag.at)]
    : from && to && months.includes(from) && months.includes(to) ? [months.indexOf(from), months.indexOf(to)] : null;
  const y = (v: number) => HEIGHT - 18 - ((v - low) / (top - low || 1)) * (HEIGHT - 32);
  const path = (xs: (number | null)[]) => xs.map((v, i) => (v === null ? "" : `${i === 0 || xs[i - 1] === null ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`)).join(" ");
  const change = mine.recent_vs_before[kpi];
  const everyoneChange = everyone.recent_vs_before[kpi];
  const sign = spec.higherIsBetter ? 1 : -1;
  const slack = kpi === "nps" || kpi === "churn_rate" ? 0 : WORSE_THAN_ALL_BY;
  const declining = change !== null && sign * change < -spec.declineAt && (everyoneChange === null || sign * change < sign * everyoneChange - slack);
  return (
    <div className="card" style={{ borderTop: "3px solid var(--cta)" }}>
      <div className="card-title" style={{ margin: 0 }}>{spec.label} over time</div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center", marginTop: 6 }}>
        <span className="card-sub">Period:</span>
        {PRESETS.map((n) => {
          const start = months[months.length - n];
          return (
            <button key={n} className={`btn btn-ghost${from === start && to === months[months.length - 1] ? " active" : ""}`}
                    style={{ padding: "2px 10px", fontSize: 12 }} onClick={() => onPeriod(start, months[months.length - 1])}>Last {n} months</button>
          );
        })}
        {from && <button className="btn btn-ghost" style={{ padding: "2px 10px", fontSize: 12 }} onClick={() => onPeriod("", "")}>Whole history</button>}
        <span className="card-sub">or drag across the graph</span>
      </div>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={`${spec.label} per month`} style={{ width: "100%", height: "auto", marginTop: 6, touchAction: "pan-y", cursor: "crosshair" }}
           onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); const i = monthAt(e); setDrag({ anchor: i, at: i }); }}
           onPointerMove={(e) => drag && setDrag({ ...drag, at: monthAt(e) })}
           onPointerUp={(e) => { if (drag) { const end = monthAt(e); const [a, b] = [Math.min(drag.anchor, end), Math.max(drag.anchor, end)];
             if (!(a === 0 && b === months.length - 1)) onPeriod(months[a], months[b]); setDrag(null); } }}>
        {chosen && <rect x={x(chosen[0]) - 4} width={x(chosen[1]) - x(chosen[0]) + 8} y={4} height={HEIGHT - 22} fill="var(--aito-teal)" opacity="0.14" />}
        <line x1="10" x2={WIDTH - 10} y1={y(0)} y2={y(0)} stroke="var(--border)" />
        <path d={path(scaled)} fill="none" stroke="var(--text-muted)" strokeWidth="1.5" strokeDasharray="4 3" />
        <path d={path(series)} fill="none" stroke="var(--aito-teal)" strokeWidth="2.5" />
        {mine.months.map((m, i) => (i % 3 === 0 || i === mine.months.length - 1) && (
          <text key={m} x={x(i)} y={HEIGHT - 3} fontSize="10" textAnchor="middle" fill="var(--text-muted)">{m}</text>
        ))}
      </svg>
      <div className="card-sub" style={{ lineHeight: 1.5 }}>
        {spec.trendNote.charAt(0).toUpperCase() + spec.trendNote.slice(1)}. Solid: this segment. Dashed: everyone, scaled to the segment&apos;s average, to compare the shape.{" "}
        {kpi === "nps" || kpi === "churn_rate" ? "Now against three months earlier" : "Last three months against the three before"}:{" "}
        <strong style={{ color: declining ? "var(--cta)" : undefined }}>{change === null ? "–" : spec.change(change)}</strong>
        {view.conditions.length > 0 && <> (everyone {everyoneChange === null ? "–" : spec.change(everyoneChange)})</>}
        {declining ? ": falling faster than the shop as a whole." : "."}
      </div>
    </div>
  );
}
