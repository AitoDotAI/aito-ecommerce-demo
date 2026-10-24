import type { HeldOutAccuracy } from "@/lib/evidence-types";
import { pct, pctInterval } from "@/lib/use-evidence";

/**
 * One held-out accuracy against its baselines, with the sentences the
 * result file worded (ADR 0037 §2). Used for the models that moved here
 * from the 360° views: Churn (Retention) and Demand (Supply).
 */
export default function HeldOutCard({
  title,
  result,
  baselines,
}: {
  title: string;
  result: HeldOutAccuracy;
  baselines: Array<[string, number]>;
}) {
  return (
    <div className="card">
      <div className="card-title" style={{ marginBottom: 4 }}>{title}</div>
      <div className="card-sub" style={{ fontFamily: "var(--mono)", fontSize: 11, marginBottom: 10 }}>
        predict <code>{result.predict}</code> from <code>{result.table}</code>
      </div>
      <table className="data-table">
        <tbody>
          <tr>
            <td style={{ fontWeight: 600 }}>Aito</td>
            <td style={{ textAlign: "right", fontFamily: "var(--mono)", fontWeight: 600 }}>
              {pct(result.accuracy)}{" "}
              <span style={{ fontWeight: 400, color: "var(--text-muted)" }}>
                {pctInterval(result.accuracy_low, result.accuracy_high)}
              </span>
            </td>
          </tr>
          {baselines.map(([label, accuracy]) => (
            <tr key={label}>
              <td style={{ color: "var(--text-2)" }}>{label}</td>
              <td style={{ textAlign: "right", fontFamily: "var(--mono)", color: "var(--text-muted)" }}>{pct(accuracy)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <ul className="verdict-list" style={{ marginTop: 10 }}>
        {result.comparisons.map((c) => <li key={c.baseline}>{c.sentence}</li>)}
      </ul>
      <div className="card-sub" style={{ marginTop: 10, lineHeight: 1.5 }}>{result.method} n = {result.n}.</div>
    </div>
  );
}
