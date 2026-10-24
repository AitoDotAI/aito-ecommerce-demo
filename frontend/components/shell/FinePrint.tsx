"use client";

import type { ReactNode } from "react";

import { useShell } from "./ShellState";

/** A view's fine print: the method, the sample sizes, the second and third
 *  caveat. Shown in place, except in demo mode (lib/demo-mode.ts), where it
 *  folds behind "Details" so the view keeps one plain caveat line. Folded,
 *  never removed: honesty stays one click away. */
export default function FinePrint({ children, summary = "Details" }: { children: ReactNode; summary?: string }) {
  const { demoMode } = useShell();
  if (!demoMode) return <>{children}</>;
  return (
    <details className="fine-print">
      <summary>{summary}</summary>
      {children}
    </details>
  );
}
