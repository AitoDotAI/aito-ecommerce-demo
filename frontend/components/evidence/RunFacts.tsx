import type { ReactNode } from "react";

import type { EvidenceRun } from "@/lib/evidence-types";

const REPO = "https://github.com/AitoDotAI/aito-ecommerce-demo/blob/main/";

export interface SourceLink { label: string; path: string }

/**
 * What produced an Evidence page's numbers (ADR 0037 §2): the method, n,
 * the run's date, the Aito version, and links to the script and the ADR.
 * Every Evidence page shows one, under its first numbers.
 */
export default function RunFacts({
  run,
  n,
  method,
  sources,
}: {
  run: EvidenceRun;
  n: string;
  method: ReactNode;
  sources: SourceLink[];
}) {
  const engine = run.aito_version
    ? `Aito ${run.aito_version}${run.aito_env ? `, env ${run.aito_env}` : ""}`
    : "Aito version not recorded";
  return (
    <div className="card" style={{ marginTop: 16 }}>
      <div className="card-title" style={{ marginBottom: 8 }}>How this was measured</div>
      <div style={{ fontSize: 13, lineHeight: 1.6, color: "var(--text-2)" }}>{method}</div>
      <dl className="run-facts">
        <dt>n</dt><dd>{n}</dd>
        <dt>Run</dt><dd>{run.date} · {engine} · code {run.code_commit}</dd>
        <dt>Re-run</dt><dd><code>{run.command}</code>{run.derived_by && <>, then <code>{run.derived_by}</code></>}</dd>
        <dt>Sources</dt>
        <dd>
          {sources.map((s, i) => (
            <span key={s.path}>
              {i > 0 && " · "}
              <a href={`${REPO}${s.path}`} target="_blank" rel="noreferrer">{s.label}</a>
            </span>
          ))}
        </dd>
      </dl>
    </div>
  );
}
