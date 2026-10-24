"use client";

import { useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";

export type EvidenceEntry = "search-relevance" | "model-checks" | "personalised-search";

/** An Evidence page's committed result file (ADR 0037 §2), or the error that kept it away. */
export function useEvidence<T>(entry: EvidenceEntry): { data: T | null; error: string | null } {
  const [state, setState] = useState<{ data: T | null; error: string | null }>({ data: null, error: null });
  useEffect(() => {
    let current = true;
    apiFetch<T>(`/api/evidence/${entry}`).then(
      (data) => { if (current) setState({ data, error: null }); },
      (e) => { if (current) setState({ data: null, error: String(e) }); },
    );
    return () => { current = false; };
  }, [entry]);
  return state;
}

export const pct = (v: number, digits = 1) => `${(v * 100).toFixed(digits)} %`;

/** A 95 % interval as "[61.2, 66.0]" in percent. */
export const pctInterval = (low: number | null, high: number | null) =>
  low === null || high === null ? "[n/a]" : `[${(low * 100).toFixed(1)}, ${(high * 100).toFixed(1)}]`;
