"use client";

import { Suspense, useCallback, useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";
import { evaluationPanel } from "@/lib/panel-content";
import { usePagePanel, useShell } from "@/components/shell/ShellState";
import ErrorState from "@/components/shell/ErrorState";
import EvidenceHeader from "@/components/evidence/EvidenceHeader";
import type { EvalResponse, EvalModelResult } from "@/lib/types";
import { useUrlState } from "@/lib/use-url-state";


/**
 * Model checks (ADR 0041; called Evaluation before) — `_evaluate` models
 * in a pass/fail table.
 * Return Risk is the engineered honest-failure case (ADR 0010);
 * the row tints red with `eval-row-fail`.
 *
 * Clicking a row updates the Aito panel's `query` block with that
 * model's actual `_evaluate` body — so a viewer can see which
 * features were held out for which target.
 */
function ModelChecksView() {
  usePagePanel(evaluationPanel(), {
    title: "Model checks",
    description:
      "Held-out accuracy per prediction model. The honest-failure row " +
      "(Return Risk) shows Aito's value: it tells you when it doesn't know.",
    breadcrumb: "Evidence › Model checks",
  });

  const { setPanel } = useShell();
  const [data, setData] = useState<EvalResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [modelParam, setModelParam] = useUrlState("model", "");

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch<EvalResponse>("/api/evaluation");
      setData(res);
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

  // The focused row: the one named in the URL, else the failing row (the
  // load-bearing demo moment a sales viewer should land on), else the first.
  const focused = data?.models.find((m) => m.id === modelParam)
    ?? data?.models.find((m) => m.verdict === "fail")
    ?? data?.models[0];
  const focusedId = focused?.id ?? null;
  const returnRisk = data?.models.find((m) => m.id === "return_risk");
  // A link naming a model that isn't in the evaluation says so, rather
  // than quietly focusing another row.
  const unknownModel = data && modelParam && !data.models.some((m) => m.id === modelParam)
    ? modelParam : null;
  useEffect(() => {
    if (focused) updatePanel(focused);
  }, [focused, updatePanel]);

  return (
    <div className="fade-in">
      <EvidenceHeader title="Model checks" data="Synthetic">
        Held-out accuracy per prediction model, against always guessing the most common value.{" "}
        <strong>Pass</strong> when Aito&apos;s accuracy beats that baseline by ≥ 10 pp.{" "}
        <strong>Fail</strong> means Aito is honestly telling you it doesn&apos;t know, even when the raw
        accuracy is high.
      </EvidenceHeader>
      {unknownModel && (
        <div className="card-sub" role="status" style={{ marginBottom: 12, color: "var(--red)" }}>
          No model “{unknownModel}” in this evaluation; showing {focused?.id} instead.
        </div>
      )}

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
            · {data.total_response_ms} ms · {data.models.length} parallel `_evaluate` calls
          </span>
        </div>
      )}

      {!error && (
        <div className="card" style={{ overflowX: "auto" }}>
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
                    Loading the evaluation…
                  </td>
                </tr>
              )}
              {!loading && data?.models.map((m) => (
                <tr
                  key={m.id}
                  className={m.verdict === "pass" ? "eval-row-pass" : "eval-row-fail"}
                  onClick={() => setModelParam(m.id)}
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

      {!error && returnRisk && returnRisk.verdict === "fail" && (
        <div className="tip-box" style={{ marginTop: 16 }}>
          <span className="tip-icon" aria-hidden="true">💡</span>
          <span>
            <strong>The failure that earns trust:</strong> Return Risk&apos;s
            accuracy looks impressive ({(returnRisk.accuracy * 100).toFixed(0)} %), but the baseline
            gets {(returnRisk.base_accuracy * 100).toFixed(0)} % by always guessing &ldquo;not
            returned&rdquo;. Aito learned nothing the baseline didn&apos;t already know, and says
            so: &ldquo;I can&apos;t predict this from your current data.&rdquo;
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


// The view reads its state from the URL (`useUrlState`), which the static
// export only allows under a Suspense boundary.
export default function ModelChecksPage() {
  return (
    <Suspense>
      <ModelChecksView />
    </Suspense>
  );
}
