"use client";

import { useEffect, useState } from "react";

import { AITO_CALLS_EVENT, type AitoCallsEvent } from "@/lib/api";


interface LatencyState {
  ms: number;       // sum of all Aito calls in the most-recent request
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
      const ms = detail.calls.reduce((s, c) => s + c.ms, 0);
      setState({
        ms,
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
        className="pill pill-grey"
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
      className="pill pill-green"
      style={{ fontFamily: "var(--mono)", fontSize: 11 }}
      title={`Aito round-trip time across ${state.count} call${state.count === 1 ? "" : "s"}`}
    >
      <span style={{ marginRight: 4, color: "var(--green)" }}>aito</span>
      {fmtMs(state.ms)}
      {state.count > 1 && (
        <span style={{ marginLeft: 4, color: "var(--text-muted)" }}>×{state.count}</span>
      )}
    </span>
  );
}
