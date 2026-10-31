"use client";

import { fmtEur } from "@/lib/api";
import { OUTCOME_HELP, OUTCOME_LABEL, type Outcome, type Run, type RunStep } from "@/lib/shopkeeper";

const OUTCOMES: Outcome[] = ["act", "suggest", "never_auto", "quiet"];
const COLOUR: Record<Outcome, string> = {
  act: "var(--aito-teal)", suggest: "var(--cta)", never_auto: "var(--cta)", quiet: "var(--text-muted)",
};

type Decisions = Record<string, "approved" | "rejected">;

/** The selected run: the agent's summary, then each step with the gate's outcome and the numbers behind it. */
export default function RunPane({ run, decisions, onDecide }: {
  run: Run; decisions: Decisions; onDecide: (key: string, choice: "approved" | "rejected" | null) => void;
}) {
  const { tally } = run;
  const acted = tally.act.expected_net_eur;
  const waiting = tally.suggest.expected_net_eur + tally.never_auto.expected_net_eur;
  return (
    <div>
      {run.stale && (
        <div className="card" style={{ borderLeft: "4px solid var(--cta)" }}>
          This run is stale: {run.stale_reason}. Its numbers are not current.
        </div>
      )}
      <div className="card" style={{ marginBottom: 12 }}>
        <div className="card-title">{run.title} · customers as of {run.as_of_month}</div>
        <div style={{ fontSize: 14, lineHeight: 1.6 }}>
          I went through the {run.steps.length} customers most likely to leave. I acted on <strong>{tally.act.steps}</strong>,
          expecting <strong>{fmtEur(acted)}</strong> more than doing nothing. <strong>{tally.suggest.steps + tally.never_auto.steps}</strong> are
          waiting for you, holding {fmtEur(waiting)} expected. I stayed quiet on <strong>{tally.quiet.steps}</strong>.
        </div>
        <div className="card-sub" style={{ marginTop: 8 }}>
          Simulated: nothing was sent. Euros are expected values from Aito&apos;s predictions, not results. Source: {run.source}.
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
          {OUTCOMES.map((o) => (
            <span key={o} title={OUTCOME_HELP[o]} style={{ border: `1px solid ${COLOUR[o]}`, borderRadius: 12, padding: "2px 10px", fontSize: 12 }}>
              {OUTCOME_LABEL[o]} {tally[o].steps}
            </span>
          ))}
        </div>
      </div>
      {run.steps.map((step) => (
        <StepCard key={step.customer_id} step={step} minRows={run.settings.in_force.min_rows} decision={decisions[`${run.id}:${step.customer_id}`]}
          onDecide={(choice) => onDecide(`${run.id}:${step.customer_id}`, choice)} />
      ))}
    </div>
  );
}

function StepCard({ step, minRows, decision, onDecide }: {
  step: RunStep; minRows: number; decision?: "approved" | "rejected"; onDecide: (choice: "approved" | "rejected" | null) => void;
}) {
  const { best } = step;
  const queued = step.outcome === "suggest" || step.outcome === "never_auto";
  return (
    <div className="card" style={{ marginBottom: 10, borderLeft: `4px solid ${COLOUR[step.outcome]}` }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
        <strong>{step.name}</strong>
        <span style={{ color: COLOUR[step.outcome], fontWeight: 600 }}>{OUTCOME_LABEL[step.outcome]}</span>
      </div>
      <div style={{ fontSize: 14, marginTop: 4 }}>
        {step.outcome === "quiet" ? <>Best candidate: </> : <>Proposed: </>}
        <strong>{best.label}</strong> · +{(best.purchase_lift_p * 100).toFixed(0)} points chance to order
        ({(step.none_purchase_p * 100).toFixed(0)} % → {(best.purchase_p * 100).toFixed(0)} %)
        · expected {fmtEur(best.net_vs_none_eur, 2)} over no action, after {fmtEur(best.cost_eur, 2)} cost
      </div>
      <div className="card-sub" style={{ marginTop: 4 }}>{step.reason}</div>
      <details style={{ marginTop: 6 }}>
        <summary className="card-sub" style={{ cursor: "pointer" }}>Why, and what else was considered</summary>
        <div className="card-sub" style={{ lineHeight: 1.6 }}>
          Situation: {Object.entries(step.context).map(([k, v]) => `${k.replace("_", " ")} ${v}`).join(" · ")}.<br />
          Aito estimates the lift from the whole action table. {step.rows} past rows match this exact situation and {best.label.toLowerCase()}
          ({step.rows_no_action} of no action); the gate asks for {minRows}, as a check that the situation has history.
          Spent {fmtEur(step.spend_12m_eur)} in 12 months; an order is about {fmtEur(step.order_value_eur)}.
          {step.tells.length > 0 && <><br />Observed: {step.tells.join("; ")}.</>}
          <br />Others: {step.alternatives.map((a) => `${a.label} ${fmtEur(a.net_vs_none_eur, 2)}`).join(" · ")}
        </div>
      </details>
      {queued && (
        <div style={{ marginTop: 8, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          {decision ? (
            <>
              <span>{decision === "approved" ? "Approved (simulated send)" : "Rejected"}</span>
              <button className="btn" onClick={() => onDecide(null)}>Undo</button>
            </>
          ) : (
            <>
              <button className="btn" onClick={() => onDecide("approved")}>Approve</button>
              <button className="btn" onClick={() => onDecide("rejected")}>Reject</button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
