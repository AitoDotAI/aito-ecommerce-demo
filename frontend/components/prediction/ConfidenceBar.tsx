"use client";

import { confClass } from "@/lib/api";

interface ConfidenceBarProps {
  /** Confidence as a fraction 0..1 */
  value: number;
  /** Track width in px, default 60 */
  width?: number;
}

/**
 * Horizontal bar showing a predicted value's probability against
 * baseline. Used in tabular contexts where space matters.
 *
 * Tier colours are demo-wide (CLAUDE.md §design system): high
 * (≥ 0.80) green, mid (0.50–0.80) yellow, low (< 0.50) red.
 */
export default function ConfidenceBar({ value, width = 60 }: ConfidenceBarProps) {
  const pct = Math.round(value * 100);
  const tier = confClass(value);
  return (
    <div className={`conf ${tier}`}>
      <div className="conf-track" style={{ width }}>
        <div className="conf-fill" style={{ width: `${pct}%` }} />
      </div>
      <span className="conf-val">{pct}%</span>
    </div>
  );
}
