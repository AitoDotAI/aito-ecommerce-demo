"use client";

import { fmtEur } from "@/lib/api";
import { OUTCOME_HELP, OUTCOME_LABEL, type Outcome, type StockRun, type StockSettings, type StockStep } from "@/lib/shopkeeper";

const OUTCOMES: Outcome[] = ["act", "suggest", "never_auto", "quiet"];
const COLOUR: Record<Outcome, string> = { act: "var(--aito-teal)", suggest: "var(--cta)", never_auto: "var(--cta)", quiet: "var(--text-muted)" };
const SHOWN = 40;

type Decisions = Record<string, "approved" | "rejected">;

/**
 * The stock routine's run (ADR 0057): a rule over what Supply serves, with the store's settings above it. It orders nothing: a reorder
 * line it acts on is simulated, and what it only suggests or leaves to a person waits for an approval that is kept in this browser.
 */
export default function StockRunPane({ run, settings, onSettings, decisions, onDecide }: {
  run: StockRun; settings: StockSettings; onSettings: (next: StockSettings) => void; decisions: Decisions;
  onDecide: (key: string, choice: "approved" | "rejected" | null) => void;
}) {
  const { tally } = run;
  const waiting = tally.suggest.order_cost_eur + tally.never_auto.order_cost_eur;
  const changed = JSON.stringify(settings) !== JSON.stringify(run.settings.recommended);
  const number = (label: string, key: keyof StockSettings, step: number, help: string) => (
    <label style={{ display: "grid", gap: 2, fontSize: 13 }}>
      <span>{label}</span>
      <input type="number" min={0} step={step} value={settings[key]} onChange={(e) => onSettings({ ...settings, [key]: Number(e.target.value) })}
             style={{ font: "inherit", padding: "3px 8px", width: 110 }} />
      <span className="card-sub" style={{ fontSize: 11, maxWidth: 220 }}>{help}</span>
    </label>
  );
  const ordered = [...run.steps].sort((a, b) => OUTCOMES.indexOf(a.outcome) - OUTCOMES.indexOf(b.outcome));
  return (
    <div>
      <div className="card" style={{ marginBottom: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <div className="card-title" style={{ margin: 0 }}>When the rule orders · the store&apos;s settings</div>
          {changed && <button className="btn btn-ghost" style={{ padding: "2px 10px", fontSize: 12 }} onClick={() => onSettings(run.settings.recommended)}>Reset to recommended</button>}
        </div>
        <div style={{ display: "flex", gap: 20, flexWrap: "wrap", marginTop: 10 }}>
          {number("Units sold, at least", "min_recent_units", 1, "in the planning window: fewer is too little to base an order on")}
          {number("Order limit (€)", "order_limit_eur", 50, "a larger order is always a person's")}
          {number("Urgent at stock share", "urgent_share", 0.1, "of the reorder point: at or below it the rule acts, above it suggests (0 to 1)")}
        </div>
      </div>
      {run.stale && <div className="card" style={{ borderLeft: "4px solid var(--cta)" }}>This run is stale: {run.stale_reason}.</div>}
      <div className="card" style={{ marginBottom: 12 }}>
        <div className="card-title">{run.title} · Supply as of {run.as_of_month}</div>
        <div style={{ fontSize: 14, lineHeight: 1.6 }}>
          The rule went through {run.steps.length} products. It ordered <strong>{tally.act.steps}</strong>, for <strong>{fmtEur(tally.act.order_cost_eur)}</strong>,
          protecting {fmtEur(tally.act.revenue_at_risk_eur)} of revenue at risk. <strong>{tally.suggest.steps + tally.never_auto.steps}</strong> are waiting for you
          ({fmtEur(waiting)} of orders and markdowns to approve). It stayed quiet on <strong>{tally.quiet.steps}</strong>.
        </div>
        <div className="card-sub" style={{ marginTop: 8 }}>
          Simulated: nothing was ordered or repriced. This is a rule on observed sales, not a forecast. Source: {run.source}.
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
          {OUTCOMES.map((o) => (
            <span key={o} title={OUTCOME_HELP[o]} style={{ border: `1px solid ${COLOUR[o]}`, borderRadius: 12, padding: "2px 10px", fontSize: 12 }}>{OUTCOME_LABEL[o]} {tally[o].steps}</span>
          ))}
        </div>
      </div>
      {ordered.slice(0, SHOWN).map((step) => (
        <StepCard key={`${step.kind}:${step.sku}`} step={step} decision={decisions[`${run.id}:${step.kind}:${step.sku}`]}
                  onDecide={(choice) => onDecide(`${run.id}:${step.kind}:${step.sku}`, choice)} />
      ))}
      {ordered.length > SHOWN && <div className="card-sub">{ordered.length - SHOWN} more steps, the quietest last, are not listed.</div>}
    </div>
  );
}

function StepCard({ step, decision, onDecide }: { step: StockStep; decision?: "approved" | "rejected"; onDecide: (choice: "approved" | "rejected" | null) => void }) {
  const queued = step.outcome === "suggest" || step.outcome === "never_auto";
  return (
    <div className="card" style={{ marginBottom: 10, borderLeft: `4px solid ${COLOUR[step.outcome]}` }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
        <strong>{step.name}</strong>
        <span style={{ color: COLOUR[step.outcome], fontWeight: 600 }}>{OUTCOME_LABEL[step.outcome]}</span>
      </div>
      <div style={{ fontSize: 14, marginTop: 4 }}>
        {step.kind === "reorder"
          ? <>{step.outcome === "quiet" ? "Would order: " : "Order: "}<strong>{step.order_qty} units</strong> for {fmtEur(step.order_cost_eur ?? 0)} · protects {fmtEur(step.revenue_at_risk_eur ?? 0)} of revenue · {step.supplier}, {step.lead_time_days} days</>
          : <>{step.markdown?.action === "markdown" ? "Mark down " : "Excess: "}<strong>{step.excess_units} units</strong> ({fmtEur(step.tied_capital_eur ?? 0)} tied up){step.markdown?.action === "markdown" ? ` by ${step.markdown.discount_pct} %` : ""}</>}
      </div>
      <div className="card-sub" style={{ marginTop: 4 }}>{step.reason}</div>
      {queued && (
        <div style={{ marginTop: 8, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          {decision ? (
            <>
              <span>{decision === "approved" ? "Approved (simulated)" : "Rejected"}</span>
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
