"use client";

/**
 * How sure the pattern is: the difference in points divided by its 99.7 % (or 95 %) margin. Above 1× the difference is larger
 * than chance would give; below it, it could be chance, and the more so the closer to 0×.
 */
export default function Confidence({ points, margin }: { points: number; margin: number }) {
  const ratio = margin > 0 ? Math.abs(points) / margin : 0;
  return (
    <span title={`${Math.abs(points)} points against a margin of ±${margin}`}
          style={{ fontFamily: "var(--mono)", fontSize: 12, color: ratio >= 1 ? "var(--text)" : "var(--text-muted)", whiteSpace: "nowrap" }}>
      {ratio.toFixed(1)}×
    </span>
  );
}
