"use client";

import { useCallback, useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";
import { patternExplorerPanel } from "@/lib/panel-content";
import { usePagePanel, useShell } from "@/components/shell/ShellState";
import LiftHint from "@/components/prediction/LiftHint";
import ErrorState from "@/components/shell/ErrorState";
import type { PatternResponse } from "@/lib/types";


/**
 * Pattern Explorer — ad-hoc `_relate` over `orders.line_categories`.
 *
 * Same Aito shape as Bought Together (ADR 0008) but exposes the
 * full lift band: positive (green), neutral (grey), and protective
 * (red) co-occurrences. The Aito panel updates with the live
 * `_relate` body on every anchor change.
 */
export default function PatternExplorerPage() {
  usePagePanel(patternExplorerPanel(), {
    title: "Pattern Explorer",
    description:
      "Live `_relate` over the order-categories Text column. Pick an " +
      "anchor and see what else lands in the basket — and what doesn't.",
    breadcrumb: "Pattern Explorer",
  });

  const { setPanel } = useShell();
  const [anchor, setAnchor] = useState("dog_dryfood");
  const [data, setData] = useState<PatternResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchData = useCallback(async (a: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch<PatternResponse>(
        `/api/pattern-explorer?anchor=${a}`,
      );
      setData(res);
      setPanel({
        ...patternExplorerPanel(),
        endpoints: ["_relate"],
        query: highlightQuery(res.last_query.body),
      });
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [setPanel]);

  useEffect(() => {
    fetchData(anchor);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [anchor]);

  const positive    = data?.patterns.filter((p) => p.band === "positive") ?? [];
  const neutral     = data?.patterns.filter((p) => p.band === "neutral")  ?? [];
  const protective  = data?.patterns.filter((p) => p.band === "protective") ?? [];

  return (
    <div className="fade-in">
      <div className="page-header">
        <div className="page-title">Pattern Explorer</div>
        <div className="page-desc">
          Live <code>_relate</code> over <code>orders.line_categories</code>. Bought
          Together's anchor picker, but with the full lift band on display —
          what's bought *together*, what's bought *instead*, and what's
          noise.
        </div>
      </div>

      {/* Anchor picker + latency */}
      <div className="search-wrap" style={{ flexWrap: "wrap" }}>
        <label
          htmlFor="anchor-picker"
          style={{ fontSize: 12, fontWeight: 600, color: "var(--text-muted)" }}
        >
          Anchor
        </label>
        <select
          id="anchor-picker"
          value={anchor}
          onChange={(e) => setAnchor(e.target.value)}
          className="search-input"
          style={{ paddingLeft: 12, width: "auto", minWidth: 220 }}
        >
          {(data?.available_anchors ?? [{ id: anchor, display: "Loading…" }]).map((a) => (
            <option key={a.id} value={a.id}>{a.display}</option>
          ))}
        </select>
        {data && (
          <span
            className="pill pill-grey"
            style={{ marginLeft: "auto", fontFamily: "var(--mono)", fontSize: 11 }}
          >
            {data.last_response_ms} ms
          </span>
        )}
      </div>

      {error && (
        <ErrorState
          title="Couldn't load Pattern Explorer"
          message={`Aito returned an error. ${error}`}
          command="./do load-data"
        />
      )}

      {!error && (
        <div className="card">
          <PatternTable
            title="↑ Positive cross-sells"
            sub="lift ≥ 1.5 · co-occurs more than baseline"
            rows={positive}
            loading={loading}
          />
          <PatternTable
            title="· Neutral patterns"
            sub="0.7 ≤ lift < 1.5 · noise band"
            rows={neutral}
            loading={loading}
          />
          <PatternTable
            title="↓ Protective patterns"
            sub="lift < 0.7 · bought *instead of* the anchor"
            rows={protective}
            loading={loading}
          />
        </div>
      )}

      {!error && data && (
        <div className="tip-box" style={{ marginTop: 16 }}>
          <span className="tip-icon" aria-hidden="true">💡</span>
          <span>
            <strong>The protective band is the same data as the cross-sell band.</strong>
            {" "}One <code>_relate</code> query returns both — Aito doesn't
            require you to model "what people will buy" separately from
            "what people won't". Sales narrative: "the same query that
            powers Bought Together also surfaces the anti-recommendations
            you'd never see from a popularity sort."
          </span>
        </div>
      )}
    </div>
  );
}


function PatternTable({
  title,
  sub,
  rows,
  loading,
}: {
  title: string;
  sub: string;
  rows: PatternResponse["patterns"];
  loading: boolean;
}) {
  return (
    <div style={{ marginBottom: 18 }}>
      <div className="card-title">{title}</div>
      <div className="card-sub" style={{ marginBottom: 8 }}>{sub}</div>
      {loading && (
        <div style={{ height: 36, background: "var(--border-light)", borderRadius: 4 }} />
      )}
      {!loading && rows.length === 0 && (
        <div style={{ fontSize: 12, color: "var(--text-muted)", padding: 6 }}>
          (none for this anchor)
        </div>
      )}
      {!loading && rows.map((p) => (
        <div className="hbar-row" key={p.token}>
          <div className="hbar-label" style={{ width: 200 }}>
            <div style={{ fontSize: 13, fontWeight: 600 }}>{p.label}</div>
            <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
              {p.support.f_on_condition.toLocaleString("fi-FI")} of{" "}
              {p.support.f.toLocaleString("fi-FI")} baskets
            </div>
          </div>
          <div className="hbar-wrap">
            <div
              className="hbar"
              style={{
                width: `${Math.min(100, (p.lift / 3.5) * 100)}%`,
                background:
                  p.band === "positive" ? "var(--green)" :
                  p.band === "neutral" ? "var(--border)"  :
                  "var(--red)",
              }}
            />
          </div>
          <LiftHint value={p.lift} />
        </div>
      ))}
    </div>
  );
}


// ── Panel query body pretty-printer ───────────────────────────────


function highlightQuery(body: Record<string, unknown>): string {
  function fmt(value: unknown, indent: number): string {
    const pad = "  ".repeat(indent);
    if (value === null) return `<span class="s">null</span>`;
    if (typeof value === "string") return `<span class="s">"${escape(value)}"</span>`;
    if (typeof value === "boolean") return `<span class="n">${value}</span>`;
    if (typeof value === "number") return `<span class="n">${value}</span>`;
    if (Array.isArray(value)) {
      if (value.length === 0) return "[]";
      const inner = value.map((v) => `${pad}  ${fmt(v, indent + 1)}`).join(",\n");
      return `[\n${inner}\n${pad}]`;
    }
    if (typeof value === "object") {
      const entries = Object.entries(value as Record<string, unknown>);
      if (entries.length === 0) return "{}";
      const inner = entries
        .map(([k, v]) => `${pad}  <span class="k">"${escape(k)}"</span>: ${fmt(v, indent + 1)}`)
        .join(",\n");
      return `{\n${inner}\n${pad}}`;
    }
    return String(value);
  }
  return fmt(body, 0);
}

function escape(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
