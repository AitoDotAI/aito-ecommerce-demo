"use client";

import type { GateSettings, SettingsView } from "@/lib/shopkeeper";

const KINDS: [string, string][] = [
  ["email", "Email"], ["ad", "Personalised ad"], ["discount", "Discount"], ["voucher", "Voucher"], ["apology", "Apology and credit"],
];

/** The store's gate settings (ADR 0052). They apply at once: the run is judged again with them. */
export default function GateSettingsForm({ view, value, onChange }: {
  view: SettingsView; value: GateSettings; onChange: (next: GateSettings) => void;
}) {
  const { lifts_in_runs: lifts } = view;
  const pct = (n: number) => Math.round(n * 100);
  const bar = (key: "act_lift" | "suggest_lift", label: string) => (
    <label style={{ display: "block", marginBottom: 8 }}>
      {label}: <strong>{pct(value[key])} points</strong>
      <input type="range" min={0} max={50} value={pct(value[key])} style={{ display: "block", width: "100%" }}
        onChange={(e) => {
          const next = Number(e.target.value) / 100;
          onChange(key === "act_lift"
            ? { ...value, act_lift: next, suggest_lift: Math.min(value.suggest_lift, next) }
            : { ...value, suggest_lift: next, act_lift: Math.max(value.act_lift, next) });
        }} />
    </label>
  );
  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <div className="card-title">When the agent acts · the store&apos;s settings</div>
      <div className="card-sub" style={{ marginBottom: 8 }}>
        A lift is how many points more likely a customer is to order after the action than after none.
        {lifts && <> In this run it runs from {pct(lifts.min)} to {pct(lifts.max)} points, median {pct(lifts.median)}.</>}
      </div>
      {bar("act_lift", "Act from a lift of")}
      {bar("suggest_lift", "Propose from a lift of")}
      <label style={{ display: "block", marginBottom: 8 }}>
        Enough evidence: at least{" "}
        <input type="number" min={0} max={200} value={value.min_rows} style={{ width: 64 }}
          onChange={(e) => onChange({ ...value, min_rows: Math.max(0, Number(e.target.value) || 0) })} />{" "}
        past rows of the action in the customer&apos;s exact situation
      </label>
      <div style={{ marginBottom: 8 }}>Always ask a person before:</div>
      {KINDS.map(([kind, label]) => (
        <label key={kind} style={{ marginRight: 12, whiteSpace: "nowrap" }}>
          <input type="checkbox" checked={value.never_auto.includes(kind)}
            onChange={(e) => onChange({ ...value, never_auto: e.target.checked
              ? [...value.never_auto, kind].sort() : value.never_auto.filter((k) => k !== kind) })} /> {label}
        </label>
      ))}
      <div style={{ marginTop: 10 }}>
        <button className="btn btn-ghost" onClick={() => onChange(view.recommended)}>Use the recommended settings</button>
      </div>
    </div>
  );
}
