"use client";

import { Suspense, useCallback, useEffect } from "react";

import { highlightQuery } from "@/lib/highlight-query";
import { evaluationPanel } from "@/lib/panel-content";
import { usePagePanel, useShell } from "@/components/shell/ShellState";
import ErrorState from "@/components/shell/ErrorState";
import EvidenceHeader from "@/components/evidence/EvidenceHeader";
import HeldOutCard from "@/components/evidence/HeldOutCard";
import RunFacts from "@/components/evidence/RunFacts";
import type { ModelCheck, ModelChecksFile } from "@/lib/evidence-types";
import { pct, pctInterval, useEvidence } from "@/lib/use-evidence";
import { useUrlState } from "@/lib/use-url-state";


/**
 * Model checks (ADR 0041; called Evaluation before): held-out accuracy of
 * the demo's prediction models, each against the baseline that gives it
 * meaning, from the committed `data/evidence/model-checks.json`
 * (`./do evidence model-checks`). Churn's and Demand's accuracy moved here
 * from their 360° views, which carry no accuracy numbers (ADR 0037).
 *
 * Return Risk is the engineered honest-failure case (ADR 0010); its row
 * tints red. Clicking a row shows that model's `_evaluate` body in the
 * Aito panel and puts it in the address bar.
 */
function ModelChecksView() {
  usePagePanel(evaluationPanel(), {
    title: "Model checks",
    description:
      "Held-out accuracy per prediction model, against the baseline that gives it meaning. " +
      "The honest-failure row (Return Risk) shows Aito saying when it doesn't know.",
    breadcrumb: "Evidence › Model checks",
  });

  const { setPanel } = useShell();
  const { data, error } = useEvidence<ModelChecksFile>("model-checks");
  const [modelParam, setModelParam] = useUrlState("model", "");

  const updatePanel = useCallback((m: ModelCheck) => {
    setPanel({ ...evaluationPanel(), endpoints: ["_evaluate"], query: highlightQuery(m.last_query.body) });
  }, [setPanel]);

  // The focused row: the one named in the URL, else the failing row (the
  // load-bearing demo moment a sales viewer should land on), else the first.
  const focused = data?.models.find((m) => m.id === modelParam)
    ?? data?.models.find((m) => m.verdict === "fail")
    ?? data?.models[0];
  const returnRisk = data?.models.find((m) => m.id === "return_risk");
  // A link naming a model that isn't in the evaluation says so, rather
  // than quietly focusing another row.
  const unknownModel = data && modelParam && !data.models.some((m) => m.id === modelParam) ? modelParam : null;
  useEffect(() => {
    if (focused) updatePanel(focused);
  }, [focused, updatePanel]);

  return (
    <div className="fade-in">
      <EvidenceHeader title="Model checks" data="Synthetic">
        Held-out accuracy of the predictions the demo shows, each against the simplest rule that would do
        without Aito. A catalogue model <strong>passes</strong> when it beats always guessing the most
        common value by {data?.threshold_pp ?? 10} points or more; <strong>fail</strong> means Aito is honestly
        telling you it doesn&apos;t know, even when the raw accuracy is high.
      </EvidenceHeader>
      {unknownModel && (
        <div className="card-sub" role="status" style={{ marginBottom: 12, color: "var(--red)" }}>
          No model “{unknownModel}” in this evaluation; showing {focused?.id} instead.
        </div>
      )}

      {error && <ErrorState title="Couldn't load the model checks" message={error} command="./do evidence model-checks" />}

      {!error && (
        <div className="card" style={{ overflowX: "auto" }}>
          <div className="card-title" style={{ marginBottom: 8 }}>Catalogue and returns</div>
          <table className="data-table">
            <thead>
              <tr>
                <th></th>
                <th>Model</th>
                <th>Features</th>
                <th style={{ textAlign: "right" }}>Accuracy [95 %]</th>
                <th style={{ textAlign: "right" }}>Most common value</th>
                <th style={{ textAlign: "right" }}>Gain</th>
                <th style={{ textAlign: "right" }}>n</th>
                <th>Verdict</th>
              </tr>
            </thead>
            <tbody>
              {!data && (
                <tr><td colSpan={8} style={{ color: "var(--text-muted)", fontSize: 12 }}>Loading the model checks…</td></tr>
              )}
              {data?.models.map((m) => (
                <ModelRow key={m.id} m={m} focused={focused?.id === m.id} onPick={() => setModelParam(m.id)} />
              ))}
            </tbody>
          </table>
          {data && (
            <ul className="verdict-list" style={{ marginTop: 12 }}>
              {data.models.flatMap((m) => m.comparisons.map((c) => <li key={`${m.id}-${c.baseline}`}>{c.sentence}</li>))}
            </ul>
          )}
        </div>
      )}

      {!error && returnRisk && returnRisk.verdict === "fail" && (
        <div className="tip-box" style={{ marginTop: 16 }}>
          <span className="tip-icon" aria-hidden="true">💡</span>
          <span>
            <strong>The failure that earns trust:</strong> Return Risk&apos;s accuracy looks impressive
            ({pct(returnRisk.accuracy, 0)}), but the baseline gets {pct(returnRisk.base_accuracy, 0)} by always
            guessing &ldquo;not returned&rdquo;. Aito learned nothing the baseline didn&apos;t already know, and
            says so: &ldquo;I can&apos;t predict this from your current data.&rdquo;
          </span>
        </div>
      )}

      {data && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 380px), 1fr))", gap: 16, marginTop: 16 }}>
          <HeldOutCard title="Retention: who leaves in the next 3 months" result={data.churn}
                       baselines={[["Always “stays”", data.churn.base_accuracy]]} />
          <HeldOutCard title="Supply: next month's sales range" result={data.demand}
                       baselines={[["Naive: last month's range", data.demand.naive_accuracy],
                                   ["Always the most common range", data.demand.base_accuracy]]} />
        </div>
      )}

      {data && (
        <RunFacts
          run={data.run}
          n={`${data.models.map((m) => `${m.label}: ${m.n}`).join("; ")}; churn: ${data.churn.n} customer-months; ` +
             `demand: ${data.demand.n} products in ${data.demand.test_month}`}
          method={<>
            Aito&apos;s <code>_evaluate</code> holds rows out, predicts each from the rest and counts the right answers.
            The intervals are 95 % normal intervals. A difference against a baseline treats the two accuracies as
            independent, because <code>_evaluate</code> returns totals rather than each row&apos;s answer: on the
            same rows, that interval is wider than a paired one. A difference whose interval spans 0 is a tie.
          </>}
          sources={[
            { label: "src/evidence/model_checks.py", path: "src/evidence/model_checks.py" },
            { label: "ADR 0010", path: "docs/adr/0010-evaluation.md" },
            { label: "ADR 0013 (churn)", path: "docs/adr/0013-churn-prediction.md" },
            { label: "ADR 0014 (demand)", path: "docs/adr/0014-demand.md" },
          ]}
        />
      )}
    </div>
  );
}


function ModelRow({ m, focused, onPick }: { m: ModelCheck; focused: boolean; onPick: () => void }) {
  const gainPp = m.accuracy_gain * 100;
  return (
    <tr
      className={m.verdict === "pass" ? "eval-row-pass" : "eval-row-fail"}
      onClick={onPick}
      style={{ cursor: "pointer", outline: focused ? "2px solid var(--cta)" : undefined, outlineOffset: -2 }}
    >
      <td><span className={`eval-mark ${m.verdict}`}>{m.verdict === "pass" ? "✓" : "✗"}</span></td>
      <td style={{ minWidth: 200 }}>
        <div style={{ fontWeight: 600 }}>{m.label}</div>
        <div style={{ fontSize: 11, color: "var(--text-muted)", fontFamily: "var(--mono)" }}>
          predict <code>{m.predict}</code> from <code>{m.table}</code>
        </div>
      </td>
      <td style={{ fontSize: 11, color: "var(--text-muted)", fontFamily: "var(--mono)" }}>{m.features.join(", ")}</td>
      <td style={{ textAlign: "right", fontFamily: "var(--mono)", fontWeight: 600, whiteSpace: "nowrap" }}>
        {pct(m.accuracy)}{" "}
        <span style={{ fontWeight: 400, color: "var(--text-muted)" }}>{pctInterval(m.accuracy_low, m.accuracy_high)}</span>
      </td>
      <td style={{ textAlign: "right", fontFamily: "var(--mono)", color: "var(--text-muted)" }}>{pct(m.base_accuracy)}</td>
      <td style={{ textAlign: "right", fontFamily: "var(--mono)", fontWeight: 700,
                   color: gainPp >= m.threshold_pp ? "var(--green)" : "var(--red)" }}>
        {gainPp >= 0 ? "+" : ""}{gainPp.toFixed(1)} pp
      </td>
      <td style={{ textAlign: "right", fontFamily: "var(--mono)", color: "var(--text-muted)" }}>{m.n}</td>
      <td><span className={`pill pill-${m.verdict === "pass" ? "green" : "red"}`}>{m.verdict.toUpperCase()}</span></td>
    </tr>
  );
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
