"use client";

import { useCallback, useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";
import { evaluationPanel } from "@/lib/panel-content";
import { usePagePanel, useShell } from "@/components/shell/ShellState";
import ErrorState from "@/components/shell/ErrorState";
import type { EvalResponse, EvalModelResult } from "@/lib/types";


/**
 * Evaluation — four `_evaluate` models in a pass/fail table.
 * Return Risk is the engineered honest-failure case (ADR 0010);
 * the row tints red with `eval-row-fail`.
 *
 * Clicking a row updates the Aito panel's `query` block with that
 * model's actual `_evaluate` body — so a viewer can see which
 * features were held out for which target.
 */
export default function EvaluationPage() {
  usePagePanel(evaluationPanel(), {
    title: "Evaluation",
    description:
      "Held-out accuracy per prediction model. The honest-failure row " +
      "(Return Risk) shows Aito's value: it tells you when it doesn't know.",
    breadcrumb: "Evaluation",
  });

  const { setPanel } = useShell();
  const [data, setData] = useState<EvalResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [focusedId, setFocusedId] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch<EvalResponse>("/api/evaluation");
      setData(res);
      // Default focus: the failing row. That's the load-bearing
      // demo moment and the one a sales viewer should land on.
      const failing = res.models.find((m) => m.verdict === "fail");
      const focus = failing ?? res.models[0];
      if (focus) {
        setFocusedId(focus.id);
        updatePanel(focus);
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  const updatePanel = useCallback((m: EvalModelResult) => {
    setPanel({
      ...evaluationPanel(),
      endpoints: ["_evaluate"],
      query: highlightQuery(m.last_query.body),
    });
  }, [setPanel]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return (
    <div className="fade-in">
      <div className="page-header">
        <div className="page-title">Evaluation</div>
        <div className="page-desc">
          Held-out accuracy per prediction model.
          {" "}
          <strong>Pass</strong> when Aito's accuracy beats the baseline by
          ≥ 10 pp.{" "}
          <strong>Fail</strong> means Aito is honestly telling you it
          doesn't know — even when the raw accuracy is high.
        </div>
      </div>

      {error && (
        <ErrorState
          title="Couldn't run evaluation"
          message={`Aito returned an error. ${error}`}
          command="./do load-data"
        />
      )}

      {!error && data && (
        <div className="card-sub" style={{ marginBottom: 12 }}>
          Last run: <code style={{ fontFamily: "var(--mono)" }}>{data.last_run}</code>
          <span style={{ marginLeft: 10, color: "var(--text-muted)" }}>
            · {data.total_response_ms} ms · 4 parallel `_evaluate` calls
          </span>
        </div>
      )}

      {!error && (
        <div className="card">
          <table className="data-table">
            <thead>
              <tr>
                <th></th>
                <th>Model</th>
                <th>Features</th>
                <th style={{ textAlign: "right" }}>Accuracy</th>
                <th style={{ textAlign: "right" }}>Baseline</th>
                <th style={{ textAlign: "right" }}>Gain</th>
                <th style={{ textAlign: "right" }}>n</th>
                <th>Verdict</th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr>
                  <td colSpan={8} style={{ color: "var(--text-muted)", fontSize: 12 }}>
                    Running four `_evaluate` calls — cold path is ~30 s…
                  </td>
                </tr>
              )}
              {!loading && data?.models.map((m) => (
                <tr
                  key={m.id}
                  className={m.verdict === "pass" ? "eval-row-pass" : "eval-row-fail"}
                  onClick={() => {
                    setFocusedId(m.id);
                    updatePanel(m);
                  }}
                  style={{
                    cursor: "pointer",
                    outline: focusedId === m.id ? "2px solid var(--cta)" : undefined,
                    outlineOffset: -2,
                  }}
                >
                  <td>
                    <span className={`eval-mark ${m.verdict}`}>
                      {m.verdict === "pass" ? "✓" : "✗"}
                    </span>
                  </td>
                  <td>
                    <div style={{ fontWeight: 600 }}>{m.label}</div>
                    <div style={{ fontSize: 11, color: "var(--text-muted)", fontFamily: "var(--mono)" }}>
                      predict <code>{m.predict}</code> from <code>{m.table}</code>
                    </div>
                  </td>
                  <td style={{ fontSize: 11, color: "var(--text-muted)", fontFamily: "var(--mono)" }}>
                    {m.features.join(", ")}
                  </td>
                  <td style={{ textAlign: "right", fontFamily: "var(--mono)", fontWeight: 600 }}>
                    {(m.accuracy * 100).toFixed(1)}%
                  </td>
                  <td style={{ textAlign: "right", fontFamily: "var(--mono)", color: "var(--text-muted)" }}>
                    {(m.base_accuracy * 100).toFixed(1)}%
                  </td>
                  <td
                    style={{
                      textAlign: "right",
                      fontFamily: "var(--mono)",
                      fontWeight: 700,
                      color:
                        m.accuracy_gain * 100 >= m.threshold_pp ? "var(--green)" : "var(--red)",
                    }}
                  >
                    {(m.accuracy_gain * 100 >= 0 ? "+" : "")}
                    {(m.accuracy_gain * 100).toFixed(1)}pp
                  </td>
                  <td style={{ textAlign: "right", fontFamily: "var(--mono)", color: "var(--text-muted)" }}>
                    {m.n}
                  </td>
                  <td>
                    <span className={`pill pill-${m.verdict === "pass" ? "green" : "red"}`}>
                      {m.verdict.toUpperCase()}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!error && data && (
        <div className="tip-box" style={{ marginTop: 16 }}>
          <span className="tip-icon" aria-hidden="true">💡</span>
          <span>
            <strong>The failure that earns trust:</strong> Return Risk's
            accuracy looks impressive (~96 %) but its <em>gain</em> is
            zero — Aito learned nothing the prior didn't already know
            (≈ 3 % of lines get returned, regardless of features). That's
            the model honestly telling you "I can't predict this from
            your current data." Better than a fake high-accuracy score
            on a production deployment.
          </span>
        </div>
      )}
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
