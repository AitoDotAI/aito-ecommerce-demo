"use client";

import type { GateSettings, SettingsView } from "@/lib/shopkeeper";

const KINDS: [string, string][] = [
  ["email", "Email"], ["ad", "Ad"], ["discount", "Discount"], ["voucher", "Voucher"], ["apology", "Apology + credit"],
];
const SCALE_MAX = 50;  // points of lift shown on the scale

const pct = (n: number) => Math.round(n * 100);
const at = (points: number) => `${Math.min(100, (points / SCALE_MAX) * 100)}%`;

/**
 * The store's gate settings (ADR 0052). One scale shows the three zones the lift bars make (stay quiet,
 * propose, act) with a dot for each customer in the run, so moving a bar shows who changes zone. The
 * settings apply at once: the run is judged again with them.
 */
export default function GateSettingsForm({ view, value, onChange, lifts }: {
  view: SettingsView; value: GateSettings; onChange: (next: GateSettings) => void; lifts: number[];
}) {
  const suggest = pct(value.suggest_lift);
  const act = pct(value.act_lift);
  const changed = JSON.stringify(value) !== JSON.stringify(view.recommended);
  const setBar = (key: "act_lift" | "suggest_lift", points: number) => {
    const next = points / 100;
    onChange(key === "act_lift"
      ? { ...value, act_lift: next, suggest_lift: Math.min(value.suggest_lift, next) }
      : { ...value, suggest_lift: next, act_lift: Math.max(value.act_lift, next) });
  };
  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <div className="card-title" style={{ margin: 0 }}>When the agent acts · the store&apos;s settings</div>
        {changed && <button className="btn btn-ghost" style={{ padding: "2px 10px", fontSize: 12 }}
          onClick={() => onChange(view.recommended)}>Reset to recommended</button>}
      </div>
      <div className="card-sub" style={{ margin: "4px 0 14px" }}>
        Lift: how many points more likely a customer is to order after the action than after none. Each dot is a customer in this run.
      </div>

      <div style={{ position: "relative", height: 34, borderRadius: 6, overflow: "hidden", display: "flex", border: "1px solid var(--border)" }}>
        <Zone width={at(suggest)} label="Quiet" bg="var(--border-light)" colour="var(--text-muted)" />
        <Zone width={`calc(${at(act)} - ${at(suggest)})`} label="Propose" bg="rgba(244, 162, 40, 0.28)" colour="var(--text)" />
        <Zone width={`calc(100% - ${at(act)})`} label="Act" bg="rgba(0, 168, 150, 0.28)" colour="var(--text)" />
        {lifts.map((lift, i) => (
          <span key={i} title={`${pct(lift)} points`} style={{
            position: "absolute", left: at(pct(lift)), bottom: 4, width: 6, height: 6, marginLeft: -3,
            borderRadius: "50%", background: "var(--text)", opacity: 0.55,
          }} />
        ))}
      </div>
      <Slider label="Propose from" points={suggest} onChange={(p) => setBar("suggest_lift", p)} />
      <Slider label="Act from" points={act} onChange={(p) => setBar("act_lift", p)} />

      <div style={{ display: "flex", alignItems: "center", gap: 10, margin: "14px 0 12px", flexWrap: "wrap" }}>
        <span style={{ fontSize: 13 }}>Enough evidence</span>
        <Stepper value={value.min_rows} onChange={(n) => onChange({ ...value, min_rows: n })} />
        <span className="card-sub">past rows matching the action and the customer&apos;s exact situation (a check: the lift is estimated from all rows)</span>
      </div>

      <div style={{ fontSize: 13, marginBottom: 6 }}>Always ask a person before sending a…</div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {KINDS.map(([kind, label]) => {
          const on = value.never_auto.includes(kind);
          return (
            <button key={kind} aria-pressed={on} onClick={() => onChange({ ...value, never_auto: on
              ? value.never_auto.filter((k) => k !== kind) : [...value.never_auto, kind].sort() })}
              style={{
                cursor: "pointer", borderRadius: 14, padding: "3px 12px", fontSize: 13, font: "inherit",
                border: `1px solid ${on ? "var(--cta)" : "var(--border)"}`,
                background: on ? "rgba(244, 162, 40, 0.18)" : "transparent", color: "var(--text)",
              }}>{on ? "✋ " : ""}{label}</button>
          );
        })}
      </div>
    </div>
  );
}

function Zone({ width, label, bg, colour }: { width: string; label: string; bg: string; colour: string }) {
  return (
    <div style={{ width, background: bg, color: colour, fontSize: 11, display: "flex", alignItems: "flex-start",
      justifyContent: "center", paddingTop: 2, overflow: "hidden", whiteSpace: "nowrap" }}>{label}</div>
  );
}

function Slider({ label, points, onChange }: { label: string; points: number; onChange: (points: number) => void }) {
  return (
    <label style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 8, fontSize: 13, flexWrap: "wrap" }}>
      <span style={{ width: 92 }}>{label}</span>
      <input type="range" min={0} max={SCALE_MAX} value={points} onChange={(e) => onChange(Number(e.target.value))}
        style={{ flex: "1 1 140px", minWidth: 0, accentColor: "var(--aito-teal)" }} />
      <strong style={{ width: 68, textAlign: "right" }}>{points} points</strong>
    </label>
  );
}

function Stepper({ value, onChange }: { value: number; onChange: (n: number) => void }) {
  const step = (d: number) => onChange(Math.max(0, Math.min(200, value + d)));
  const button = { width: 26, height: 26, cursor: "pointer", border: "1px solid var(--border)", background: "transparent", color: "var(--text)", font: "inherit" } as const;
  return (
    <span style={{ display: "inline-flex", alignItems: "center" }}>
      <button aria-label="Fewer rows" onClick={() => step(-1)} style={{ ...button, borderRadius: "6px 0 0 6px" }}>−</button>
      <span style={{ minWidth: 38, textAlign: "center", height: 26, lineHeight: "26px", fontWeight: 600,
        borderTop: "1px solid var(--border)", borderBottom: "1px solid var(--border)" }}>{value}</span>
      <button aria-label="More rows" onClick={() => step(1)} style={{ ...button, borderRadius: "0 6px 6px 0" }}>+</button>
    </span>
  );
}
