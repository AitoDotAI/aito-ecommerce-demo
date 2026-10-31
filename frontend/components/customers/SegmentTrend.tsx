"use client";

import { kpiSpec } from "@/lib/customer-kpis";
import type { KpiId, SegmentView } from "@/lib/customer-profiles";

const WIDTH = 520;
const HEIGHT = 140;
const DECLINE_BELOW = -0.05;      // a fall of more than 5 % ...
const WORSE_THAN_ALL_BY = 0.03;   // ... and 3 points worse than everyone is called a decline
const NPS_DECLINE_POINTS = -5;    // an NPS that fell more than 5 points, and more than everyone's

/** The top right: the chosen figure over the shop's months for the segment, and whether it is in decline against everyone. */
export default function SegmentTrend({ view, kpi }: { view: SegmentView; kpi: KpiId }) {
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
  const y = (v: number) => HEIGHT - 18 - ((v - low) / (top - low || 1)) * (HEIGHT - 32);
  const path = (xs: (number | null)[]) => xs.map((v, i) => (v === null ? "" : `${i === 0 || xs[i - 1] === null ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`)).join(" ");
  const change = mine.recent_vs_before[kpi];
  const everyoneChange = everyone.recent_vs_before[kpi];
  const declining = change !== null && (kpi === "nps"
    ? change < NPS_DECLINE_POINTS && (everyoneChange === null || change < everyoneChange)
    : change < DECLINE_BELOW && (everyoneChange === null || change < everyoneChange - WORSE_THAN_ALL_BY));
  return (
    <div className="card" style={{ borderTop: "3px solid var(--cta)" }}>
      <div className="card-title" style={{ margin: 0 }}>{spec.label} over time</div>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={`${spec.label} per month`} style={{ width: "100%", height: "auto", marginTop: 6 }}>
        <line x1="10" x2={WIDTH - 10} y1={y(0)} y2={y(0)} stroke="var(--border)" />
        <path d={path(scaled)} fill="none" stroke="var(--text-muted)" strokeWidth="1.5" strokeDasharray="4 3" />
        <path d={path(series)} fill="none" stroke="var(--aito-teal)" strokeWidth="2.5" />
        {mine.months.map((m, i) => (i % 3 === 0 || i === mine.months.length - 1) && (
          <text key={m} x={x(i)} y={HEIGHT - 3} fontSize="10" textAnchor="middle" fill="var(--text-muted)">{m}</text>
        ))}
      </svg>
      <div className="card-sub" style={{ lineHeight: 1.5 }}>
        {spec.trendNote.charAt(0).toUpperCase() + spec.trendNote.slice(1)}. Solid: this segment. Dashed: everyone, scaled to the segment&apos;s average, to compare the shape.{" "}
        {kpi === "nps" ? "Now against three months earlier" : "Last three months against the three before"}:{" "}
        <strong style={{ color: declining ? "var(--cta)" : undefined }}>{change === null ? "–" : spec.change(change)}</strong>
        {view.conditions.length > 0 && <> (everyone {everyoneChange === null ? "–" : spec.change(everyoneChange)})</>}
        {declining ? ": falling faster than the shop as a whole." : "."}
      </div>
    </div>
  );
}
