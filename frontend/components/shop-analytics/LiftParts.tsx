"use client";

import { useEffect, useState } from "react";

import { ApiError, apiFetch } from "@/lib/api";
import type { ShopLiftRow, ShopSignificance } from "@/lib/types";


/** One section's request: its data, a bad link (400), or another error. */
export function useSection<T>(path: string): { data: T | null; badLink: string | null; error: string | null } {
  const [state, setState] = useState<{ data: T | null; badLink: string | null; error: string | null }>(
    { data: null, badLink: null, error: null });
  useEffect(() => {
    // Only the request for the state now in the URL may update the section.
    let current = true;
    setState({ data: null, badLink: null, error: null });
    apiFetch<T>(path).then((data) => {
      if (current) setState({ data, badLink: null, error: null });
    }, (e) => {
      if (!current) return;
      if (e instanceof ApiError && e.status === 400) setState({ data: null, badLink: e.serverMessage ?? e.message, error: null });
      else setState({ data: null, badLink: null, error: String(e) });
    });
    return () => { current = false; };
  }, [path]);
  return state;
}


const FIELD_LABELS: Record<string, string> = {
  "product_sku.rating_band": "rating", "product_sku.category": "category", "product_sku.dietary": "dietary line",
  "context.customer.pets": "declared pets", "context.customer.diet": "declared diet",
  "context.surface": "surface", "context.search_query": "search word", just_bought: "in their last order",
  "product_state.on_offer": "on offer", "product_state.discount_band": "discount",
  "product_state.age": "new or established", "product_state.rival_launched": "a rival launched",
  "product_state.price_change": "price change",
};
export const fieldLabel = (field: string) => FIELD_LABELS[field] ?? field;

export function valueLabel(row: ShopLiftRow): string {
  if (row.field === "just_bought") return row.value === "true" ? "yes" : "no";
  if (row.field === "product_sku.rating_band") return row.value === "unrated" ? "unrated" : `${row.value.replace("-", "–")} stars`;
  return row.value.replace(/[_-]/g, " ");
}

export function LiftList({ rows, unit }: { rows: ShopLiftRow[]; unit: string }) {
  if (rows.length === 0) return <div className="card-sub">No lift clears the bar below.</div>;
  return (
    <>
      {rows.map((r) => (
        <Row key={`${r.field}-${r.value}`} lift={r.lift} low={r.interval_low} high={r.interval_high}
             label={<><span style={{ color: "var(--text-muted)" }}>{fieldLabel(r.field)}</span> = {valueLabel(r)}</>}
             counts={`${fmt(r.rows_with_value)} of ${fmt(r.condition_rows)} ${unit}`} />
      ))}
    </>
  );
}

export function Row({ label, lift, low, high, counts }: {
  label: React.ReactNode; lift: number; low: number; high: number; counts: string;
}) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 12, padding: "5px 0", fontSize: 13 }}>
      <span>
        {label}
        <span style={{ color: "var(--text-muted)", fontSize: 11 }}> · {counts}</span>
      </span>
      <span style={{ whiteSpace: "nowrap" }}>
        <strong style={{ color: lift > 1 ? "var(--green)" : "var(--red)" }}>{lift.toFixed(2)}×</strong>
        <span style={{ color: "var(--text-muted)", fontSize: 11 }}> {low.toFixed(2)}–{high.toFixed(2)}</span>
      </span>
    </div>
  );
}

/** What the threshold guarantees, in one line under each section. */
export function Threshold({ significance, designEffect }: { significance: ShopSignificance; designEffect: string }) {
  const level = Math.round(significance.family_confidence * 100);
  return (
    <div className="card-sub" style={{ marginTop: 10, fontSize: 11 }}>
      {significance.tested} lifts had ≥ 30 independent rows and were tested. Shown: interval clear of 1 at {level} %
      for the section as a whole (Bonferroni, z = {significance.z.toFixed(2)}), widened for {designEffect}.
      A lift not shown may still be real.
    </div>
  );
}

export function NoClearEffect({ fields }: { fields: string[] }) {
  if (fields.length === 0) return null;
  return (
    <div className="card-sub" style={{ marginTop: 8 }}>
      No clear effect (nothing cleared the bar, or too few independent rows): {fields.map(fieldLabel).join(", ")}
    </div>
  );
}

export function More({ count, what }: { count: number; what: string }) {
  if (count <= 0) return null;
  return <div className="card-sub" style={{ fontSize: 11 }}>+{count} more {what}</div>;
}

export function Card({ title, sub, controls, children }: {
  title: string; sub: string; controls?: React.ReactNode; children: React.ReactNode;
}) {
  return (
    <div className="card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <div className="page-title" style={{ fontSize: 16, margin: "0 0 4px" }}>{title}</div>
        {controls}
      </div>
      <div className="card-sub" style={{ marginBottom: 12 }}>{sub} · lift, then its interval</div>
      {children}
    </div>
  );
}

export const fmt = (n: number) => n.toLocaleString("en-US");
export const pct = (share: number) => `${(share * 100).toFixed(1)} %`;
