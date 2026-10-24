import React from "react";

import type { WhyEstimatePayload } from "@/lib/types";

/**
 * The body of the `?` popover for a k-NN `_estimate` (Demand, Inventory).
 *
 * The backend (`src/estimate_why.py`) splits Aito's neighbour average into
 * a base, one row per field, the similar past months and any gap to the
 * estimate. The rows chain: each one adds units (form "add") or multiplies
 * them (form "multiply"), and the running total ends at the estimate.
 * A percentage is shown only for a real multiplier.
 */
export default function EstimateWhyBody({ why }: { why: WhyEstimatePayload }) {
  return (
    <>
      <div style={{
        background: "var(--bg)", padding: "10px 12px", borderRadius: 6, marginBottom: 10,
        display: "flex", justifyContent: "space-between", alignItems: "center",
      }}>
        <div>
          <div style={{
            fontSize: 9, fontWeight: 700, textTransform: "uppercase",
            letterSpacing: 0.6, color: "var(--text-muted)",
          }}>
            Expected value
          </div>
          <div style={{ fontSize: 11, color: "var(--text-2)", marginTop: 2 }}>
            Aito&apos;s estimate of <strong>{why.field_label}</strong>
          </div>
        </div>
        <div style={{ fontWeight: 800, fontSize: 18, fontFamily: "var(--mono)" }}>
          {why.estimate !== null ? why.estimate.toFixed(2) : "—"}
        </div>
      </div>
      {why.form === "add" || why.form === "multiply" ? <Chain why={why} />
        : why.form === "raw" ? <Raw why={why} />
        : <Footer>
            This explanation was saved by an older version of the demo, which
            read Aito&apos;s terms on the wrong scale. Run <code>./do precompute</code>{" "}
            to refresh it.
          </Footer>}
    </>
  );
}

function Chain({ why }: { why: WhyEstimatePayload }) {
  const multiply = why.form === "multiply";
  let running = why.base ?? 0;
  return (
    <div style={{ fontSize: 12.5 }}>
      <Row label="" change="Effect" total="Units" muted />
      <Row label="A typical month in the data" change="" total={running.toFixed(2)} />
      {why.components.map((c, i) => {
        const effect = c.effect ?? 0;
        running = multiply ? running * effect : running + effect;
        const up = multiply ? effect >= 1 : effect >= 0;
        const size = multiply
          ? `${Math.abs((effect - 1) * 100).toFixed(1)} %`
          : `${Math.abs(effect).toFixed(2)} units`;
        return (
          <Row
            key={i}
            label={c.label ?? c.type}
            change={`${up ? "+" : "−"}${size}`}
            color={up ? "var(--green)" : "var(--red)"}
            total={running.toFixed(2)}
            italic={c.type === "unexplained"}
          />
        );
      })}
      <Row label="Estimate" change="" total={(why.estimate ?? running).toFixed(2)} strong />
      <Footer>
        Aito averages the {why.neighbours} past months most like this one.
        Each field row is the same in all of them; <em>similar past months</em>{" "}
        is how far those months sold above or below what their fields predict,
        on average. Each row {multiply ? "multiplies" : "adds to"} the units above it.
      </Footer>
    </div>
  );
}

function Raw({ why }: { why: WhyEstimatePayload }) {
  return (
    <div style={{ fontSize: 12.5 }}>
      <Row label="" change="Raw term" total="" muted />
      {why.components.map((c, i) => (
        <Row key={i} label={c.label ?? c.type} change={(c.effect ?? 0).toFixed(2)} total="" />
      ))}
      <Footer>
        Aito&apos;s neighbours don&apos;t share their field terms here, so the
        estimate can&apos;t be split into rows that add up. These are the top
        neighbour&apos;s terms as Aito returned them, not converted to units.
      </Footer>
    </div>
  );
}

function Row({ label, change, total, color, strong, muted, italic }: {
  label: string; change: string; total: string; color?: string;
  strong?: boolean; muted?: boolean; italic?: boolean;
}) {
  return (
    <div style={{
      display: "grid", gridTemplateColumns: "1fr 84px 52px", gap: 8, padding: "3px 0",
      fontWeight: strong ? 700 : 400, fontStyle: italic ? "italic" : undefined,
      color: muted ? "var(--text-muted)" : undefined, fontSize: muted ? 10.5 : undefined,
    }}>
      <span>{label}</span>
      <span style={{ textAlign: "right", color: muted ? undefined : color, fontFamily: "var(--mono)" }}>{change}</span>
      <span style={{ textAlign: "right", fontFamily: "var(--mono)" }}>{total}</span>
    </div>
  );
}

function Footer({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      marginTop: 8, paddingTop: 10, borderTop: "1px solid var(--border-light)",
      fontSize: 11, color: "var(--text-muted)", lineHeight: 1.5,
    }}>
      {children}
    </div>
  );
}
