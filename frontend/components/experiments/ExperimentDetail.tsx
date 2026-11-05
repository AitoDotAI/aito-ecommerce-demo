import IntervalBar from "@/components/experiments/IntervalBar";
import { ARM_LABEL, ARM_VERDICT_TEXT, KIND_LABEL, STATUS_LABEL, clearWinner, eur, rate, signedEur, type Experiment } from "@/lib/experiments";

const SHOWN = { offer: "Price", title: "Title", image: "Image" } as const;

/** One experiment: what each arm shows and earns, the difference with its interval, and where the experiment stands. */
export default function ExperimentDetail({ e }: { e: Experiment }) {
  const [control, second] = e.arms;
  const winner = clearWinner(e);
  const contradicted = e.status === "decided" && winner !== null && winner !== e.decided_arm;
  return (
    <div className="card">
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "baseline" }}>
        <div className="card-title" style={{ margin: 0 }}>{e.product}</div>
        <span className="card-sub">{KIND_LABEL[e.kind]} · {STATUS_LABEL[e.status]}</span>
      </div>
      <div className="card-sub" style={{ margin: "4px 0 10px", lineHeight: 1.5 }}>{e.hypothesis}</div>
      <div className="scroll-x">
        <table style={{ width: "100%", fontSize: 12.5, borderCollapse: "collapse" }}>
          <thead>
            <tr className="card-sub" style={{ fontSize: 11.5, textAlign: "left" }}>
              <th>Arm</th><th>{SHOWN[e.kind]} shown</th><th>Showings</th><th>Purchases</th><th>Rate</th><th title="What one sale earns on this arm">Margin per sale</th><th title="Purchase rate times margin">Profit per showing</th>
            </tr>
          </thead>
          <tbody>
            {e.arms.map((a) => (
              <tr key={a.arm} style={{ borderTop: "1px solid var(--border-light)" }}>
                <td style={{ padding: "3px 6px 3px 0", fontWeight: 600 }}>{ARM_LABEL[a.arm]}{a.is_control && <span className="card-sub"> (control)</span>}</td>
                <td style={{ paddingRight: 8, overflowWrap: "anywhere" }}>{e.kind === "offer" ? eur(a.price_eur) : e.kind === "title" ? a.title : a.image}</td>
                <td>{a.showings.toLocaleString("en-GB")}</td><td>{a.purchases.toLocaleString("en-GB")}</td>
                <td>{e.status === "draft" ? "–" : rate(a.rate)}</td><td>{eur(a.margin_eur)}</td>
                <td style={{ fontWeight: 600 }}>{e.status === "draft" ? "–" : eur(a.profit_per_showing)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {e.difference && e.verdict && (
        <div style={{ marginTop: 12 }}>
          <div style={{ fontSize: 13 }}>
            <strong>{ARM_LABEL[second.arm]} against {ARM_LABEL[control.arm]}:</strong> {signedEur(e.difference.delta)} profit per showing
            <span className="card-sub"> (95 % interval {signedEur(e.difference.interval[0])} to {signedEur(e.difference.interval[1])})</span>
          </div>
          <IntervalBar delta={e.difference.delta} interval={e.difference.interval} format={signedEur} />
          <div className="card-sub" style={{ lineHeight: 1.5 }}>{ARM_VERDICT_TEXT[e.verdict]}</div>
        </div>
      )}
      <div style={{ marginTop: 12, fontSize: 13, lineHeight: 1.5 }}>
        {e.status === "draft" && <>Draft: no showings yet. It starts with {Math.round(100 * e.allocation)} % of showings on each arm.</>}
        {e.status === "running" && <>Running since {e.started_month}: {Math.round(100 * e.allocation)} % of showings on each arm.{winner && <> The data is clear enough to decide: <strong>{ARM_LABEL[winner]}</strong>.</>}</>}
        {e.status === "decided" && e.decided_arm && (
          <>Decided in {e.decided_month}: <strong>{ARM_LABEL[e.decided_arm]}</strong> is shown {Math.round(100 * (1 - e.explore_floor))} % of the time, and the other arm still
            appears at random in the rest ({Math.round(100 * e.explore_floor)} % exploration), so the experiment keeps learning.
            {contradicted && <strong style={{ color: "var(--cta)" }}> The data since says the other arm is better.</strong>}</>
        )}
      </div>
    </div>
  );
}
