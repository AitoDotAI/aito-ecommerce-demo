import { useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";
import { ARM_LABEL, eur, signedEur, type Experiment, type Plan } from "@/lib/experiments";

const SLIDERS = [
  { key: "allocation", label: "Share of showings on the second arm while testing", min: 5, max: 95, step: 5 },
  { key: "floor", label: "Exploration floor once a winner is decided", min: 0, max: 50, step: 5 },
  { key: "guardrail", label: "Guardrail: stop the second arm if it earns this much less than the control", min: 1, max: 100, step: 1 },
] as const;

/** What-if controls (ADR 0064, slice 3): the split, floor and guardrail projected from the counted evidence. Nothing is served, so nothing changes in the Shop. */
export default function PlanControls({ e }: { e: Experiment }) {
  const [settings, setSettings] = useState({ allocation: Math.round(100 * e.allocation), floor: Math.round(100 * e.explore_floor), guardrail: 10 });
  const [plan, setPlan] = useState<Plan | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const query = `allocation=${settings.allocation / 100}&floor=${settings.floor / 100}&guardrail=${settings.guardrail}`;
    const timer = setTimeout(() => {
      apiFetch<Plan>(`/api/experiments/${e.experiment_id}/plan?${query}`).then((p) => { setPlan(p); setError(null); }).catch((failure) => setError(String(failure)));
    }, 150);
    return () => clearTimeout(timer);
  }, [e.experiment_id, settings]);

  return (
    <div className="card">
      <div className="card-title" style={{ marginTop: 0 }}>What if: split, floor and guardrail</div>
      <div className="card-sub" style={{ marginBottom: 8, lineHeight: 1.5 }}>
        A projection from the showings counted above, at the same traffic. The Shop does not serve these arms, so these controls change nothing there.
      </div>
      {SLIDERS.map((s) => (
        <label key={s.key} style={{ display: "grid", gap: 2, marginBottom: 8, fontSize: 12.5 }}>
          <span>{s.label}: <strong>{settings[s.key]} %</strong></span>
          <input type="range" min={s.min} max={s.max} step={s.step} value={settings[s.key]} onChange={(change) => setSettings({ ...settings, [s.key]: Number(change.target.value) })} />
        </label>
      ))}
      {error && <div style={{ color: "var(--cta)", fontSize: 13 }}>{error}</div>}
      {plan && !error && (
        <div style={{ fontSize: 13, lineHeight: 1.6 }}>
          <div>Testing at this split earns <strong>{eur(plan.testing.profit_per_month, 0)}</strong> a month on {Math.round(plan.monthly_showings).toLocaleString("en-GB")} showings; showing the control to everybody earns {eur(plan.all_control.profit_per_month, 0)}.</div>
          <div>Deciding <strong>{ARM_LABEL[plan.decided.arm]}</strong> now, with the floor kept on the other, earns {eur(plan.decided.profit_per_month, 0)} a month: testing costs {eur(plan.cost_of_testing_per_month, 0)} a month against that, if the measured difference holds.</div>
          <div>
            {plan.months_to_clear === 0 ? "The difference is already clear."
              : plan.months_to_clear === null ? "At this split the difference would not become clear within three years."
              : `A clear answer needs about ${plan.months_to_clear} more month${plan.months_to_clear === 1 ? "" : "s"} at this split.`}
          </div>
          <div>
            {plan.guardrail.trips ? <strong style={{ color: "var(--cta)" }}>The guardrail trips: </strong> : "The guardrail holds: "}
            the second arm's difference is at most {signedEur(plan.guardrail.upper_end_eur)} per showing, and the limit is {signedEur(plan.guardrail.limit_eur)}.
          </div>
        </div>
      )}
    </div>
  );
}
