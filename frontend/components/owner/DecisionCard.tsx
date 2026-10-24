"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import FinePrint from "@/components/shell/FinePrint";
import { useShell } from "@/components/shell/ShellState";

/**
 * The line an owner view leads with (ADR 0041): the decision, its
 * estimated impact, and where its accuracy is measured. Accuracy numbers
 * live in Evidence (ADR 0037), so the card links there instead of
 * showing one. In demo mode the note folds behind "Details".
 */
export default function DecisionCard({
  decision, impact, note, evidenceHref, tone = "act",
}: {
  decision: ReactNode;
  impact: ReactNode;
  /** Where the numbers come from, in a sentence. */
  note?: ReactNode;
  evidenceHref: string;
  tone?: "act" | "warn";
}) {
  const { demoMode } = useShell();
  const accent = tone === "act" ? "var(--aito-teal)" : "var(--cta)";
  return (
    <div className="card" style={{ borderLeft: `4px solid ${accent}` }}>
      <div className="page-title" style={{ fontSize: 19, margin: "2px 0 8px" }}>{decision}</div>
      <div style={{ fontSize: 14, lineHeight: 1.55, color: "var(--text)" }}>{impact}</div>
      <div className="card-sub" style={{ marginTop: 10, lineHeight: 1.5 }}>
        {!demoMode && note}{!demoMode && note && " "}
        <Link href={evidenceHref}>How well? →</Link>
      </div>
      {demoMode && note && <div className="card-sub"><FinePrint>{note}</FinePrint></div>}
    </div>
  );
}

/** "2026-05" → "May 2026". */
export function monthName(yyyymm: string): string {
  const [year, month] = yyyymm.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, 1)).toLocaleString("en-GB", {
    month: "long", year: "numeric", timeZone: "UTC",
  });
}
