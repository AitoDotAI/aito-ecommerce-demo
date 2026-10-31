"use client";

import { useEffect, useState } from "react";

import { AITO_CALLS_EVENT, type AitoCallsEvent } from "@/lib/api";


interface LatencyState {
  ms: number;       // the median Aito call of the most-recent request
  total: number;    // the sum of all its calls
  count: number;    // number of underlying _predict/_relate/... calls
  cached: boolean;  // true when no X-Aito-Calls header (cache hit)
}


function fmtMs(ms: number): string {
  if (ms < 10) return ms.toFixed(1) + " ms";
  if (ms < 1000) return Math.round(ms) + " ms";
  return (ms / 1000).toFixed(2) + " s";
}


/**
 * Topbar latency pill — subscribes to the `aito:calls` event the
 * `apiFetch` wrapper broadcasts. Shows the round-trip cost of the
 * most-recent API request, or "cached" when the response came back
 * with no `X-Aito-Calls` header.
 *
 * Replaces the per-view "X ms" badges that used to render the
 * server-side `last_response_ms` field — those went stale on
 * cache-hit responses (the cached DTO carries the *original* fetch's
 * timing).
 */
export default function LatencyBadge() {
  const [state, setState] = useState<LatencyState | null>(null);

  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<AitoCallsEvent>).detail;
      const sorted = detail.calls.map((c) => c.ms).sort((a, b) => a - b);
      setState({
        ms: sorted.length ? sorted[Math.floor(sorted.length / 2)] : 0,
        total: sorted.reduce((s, ms) => s + ms, 0),
        count: detail.calls.length,
        cached: detail.cached,
      });
    };
    window.addEventListener(AITO_CALLS_EVENT, handler);
    return () => window.removeEventListener(AITO_CALLS_EVENT, handler);
  }, []);

  if (!state) return null;

  if (state.cached) {
    return (
      <span
        className="pill pill-grey latency-badge"
        style={{ fontFamily: "var(--mono)", fontSize: 11 }}
        title="Cache hit — no Aito round-trip on this request"
      >
        <span style={{ marginRight: 4, color: "var(--text-muted)" }}>aito</span>
        cached
      </span>
    );
  }

  return (
    <span
      className="pill pill-green latency-badge"
      style={{ fontFamily: "var(--mono)", fontSize: 11 }}
      title={`Median Aito call of ${state.count}: ${fmtMs(state.ms)}; all together ${fmtMs(state.total)} (calls run in parallel, so the page waited less)`}
    >
      <span style={{ marginRight: 4, color: "var(--green)" }}>aito</span>
      {fmtMs(state.ms)}
      {state.count > 1 && (
        <span style={{ marginLeft: 4, color: "var(--text-muted)" }}>per call ×{state.count}</span>
      )}
    </span>
  );
}
