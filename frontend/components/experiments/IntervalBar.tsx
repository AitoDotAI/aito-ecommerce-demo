/** A difference and its 95 % interval on a line through zero: teal when the interval is above zero, orange below, grey across. */
export default function IntervalBar({ delta, interval, format }: { delta: number; interval: [number, number]; format: (value: number) => string }) {
  const reach = Math.max(Math.abs(interval[0]), Math.abs(interval[1]), Math.abs(delta)) * 1.15 || 1;
  const at = (value: number) => `${50 + (50 * value) / reach}%`;
  const colour = interval[0] > 0 ? "var(--aito-teal)" : interval[1] < 0 ? "var(--cta)" : "var(--text-muted)";
  return (
    <div role="img" aria-label={`${format(delta)}, interval ${format(interval[0])} to ${format(interval[1])}`} style={{ margin: "6px 0 2px" }}>
      <div style={{ position: "relative", height: 18 }}>
        <div style={{ position: "absolute", top: 8, left: 0, right: 0, height: 2, background: "var(--border)" }} />
        <div style={{ position: "absolute", top: 2, left: "50%", width: 1, height: 14, background: "var(--text-muted)" }} />
        <div style={{ position: "absolute", top: 5, left: at(interval[0]), width: `${(50 * (interval[1] - interval[0])) / reach}%`, height: 8, background: colour, opacity: 0.35, borderRadius: 4 }} />
        <div style={{ position: "absolute", top: 3, left: at(delta), width: 4, height: 12, marginLeft: -2, background: colour, borderRadius: 2 }} />
      </div>
      <div className="card-sub" style={{ display: "flex", justifyContent: "space-between", fontSize: 11 }}>
        <span>{format(-reach)}</span><span>0</span><span>{format(reach)}</span>
      </div>
    </div>
  );
}
