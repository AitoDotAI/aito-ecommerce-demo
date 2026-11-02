"use client";

import { Suspense, useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";
import { usePagePanel } from "@/components/shell/ShellState";
import ErrorState from "@/components/shell/ErrorState";

interface AitoNumbers { lift: number; fOnCondition?: number; fCondition?: number; f?: number; n?: number }
interface PatternRow { label: string; k: number; overall: number; p: number; lift: number | null; aito: AitoNumbers | null; products: number | null }
interface Group { title: string; rows: number; of: number; sections: Record<string, PatternRow[]> }

const SHOWN = 12;
const pct = (a: number, b: number) => (b ? `${(100 * a / b).toFixed(1)} %` : "–");
const chance = (p: number) => (p < 1e-4 ? "< 0.0001" : p.toFixed(4));

/** A prototype for judging pattern search by eye: counted numbers beside Aito's own `_relate` numbers, sorted by chance or by lift. */
function FeedbackPatterns() {
  usePagePanel(null, { title: "Feedback patterns (prototype)", description: "Which products, brands and words stand out among poor reviews and detractors.", breadcrumb: "Prototype › Feedback patterns" });
  const [data, setData] = useState<Record<string, Group> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [groupKey, setGroupKey] = useState("stars");
  const [sortBy, setSortBy] = useState<"chance" | "lift" | "aito">("chance");
  const [minRows, setMinRows] = useState(1);
  const [all, setAll] = useState(false);

  useEffect(() => { apiFetch<Record<string, Group>>("/api/feedback-patterns").then(setData).catch((e) => setError(String(e))); }, []);
  if (error) return <ErrorState title="Couldn't load the prototype" message={error} command="uv run python scripts/feedback_patterns_prototype.py" />;
  if (!data) return <div className="card" style={{ height: 160, background: "var(--border-light)" }} />;
  const group = data[groupKey];

  return (
    <div className="fade-in">
      <div className="page-header">
        <div className="page-title">Feedback patterns <span className="card-sub">(prototype)</span></div>
        <div className="page-desc">
          What is over-represented among poor reviews and detractors? Each row is a candidate pattern. <strong>Counted</strong> numbers come from searching the rows;
          <strong> Aito&apos;s</strong> numbers are what <code>_relate</code> reports for the same pattern. Sort by lift to see how rare events inflate it.
        </div>
      </div>
      <div className="card" style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "center", fontSize: 13 }}>
        {Object.entries(data).map(([key, g]) => (
          <button key={key} className="btn btn-ghost" aria-pressed={groupKey === key} onClick={() => setGroupKey(key)}
                  style={{ borderColor: groupKey === key ? "var(--aito-teal)" : undefined }}>{g.title}</button>
        ))}
        <span className="card-sub">{group.rows.toLocaleString("en-GB")} of {group.of.toLocaleString("en-GB")} rows</span>
        <label>Sort by{" "}
          <select value={sortBy} onChange={(e) => setSortBy(e.target.value as typeof sortBy)}>
            <option value="chance">chance of luck (smallest first)</option>
            <option value="lift">counted lift (largest first)</option>
            <option value="aito">Aito&apos;s lift (largest first)</option>
          </select>
        </label>
        <label>Rows with the pattern, at least{" "}
          <input type="number" min={1} value={minRows} onChange={(e) => setMinRows(Math.max(1, Number(e.target.value)))} style={{ width: 56 }} />
        </label>
        <label><input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} /> show all</label>
      </div>

      {Object.entries(group.sections).map(([section, rows]) => {
        const tests = rows.length;
        const sorted = rows.filter((r) => r.overall >= minRows).sort((a, b) =>
          sortBy === "chance" ? a.p - b.p : sortBy === "lift" ? (b.lift ?? 0) - (a.lift ?? 0) : (b.aito?.lift ?? 0) - (a.aito?.lift ?? 0));
        const clear = rows.filter((r) => r.p * tests < 0.05).length;
        return (
          <div className="card" key={section}>
            <div className="card-title">{section[0].toUpperCase() + section.slice(1)}</div>
            <div className="card-sub" style={{ marginBottom: 6 }}>
              {tests} candidates tested; {clear} clear after correcting for the number tested (chance × {tests} &lt; 0.05).
            </div>
            <div className="scroll-x">
              <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
                <thead>
                  <tr className="card-sub" style={{ fontSize: 12, textAlign: "left" }}>
                    <th>Pattern</th><th>In the group</th><th>In all rows</th><th>Counted lift</th><th>Chance of luck</th><th>Clear?</th>
                    <th style={{ color: "var(--text-muted)" }}>Aito&apos;s lift</th><th style={{ color: "var(--text-muted)" }}>Aito&apos;s counts (on condition / condition / pattern / all)</th>
                  </tr>
                </thead>
                <tbody>
                  {(all ? sorted : sorted.slice(0, SHOWN)).map((r) => (
                    <tr key={r.label} style={{ borderTop: "1px solid var(--border-light)" }}>
                      <td style={{ padding: "3px 8px 3px 0" }}>{r.label}{r.products ? <span className="card-sub"> · {r.products} products</span> : null}</td>
                      <td>{r.k} ({pct(r.k, group.rows)})</td>
                      <td>{r.overall} ({pct(r.overall, group.of)})</td>
                      <td>{r.lift === null ? "–" : r.lift.toFixed(1)}</td>
                      <td>{chance(r.p)}</td>
                      <td style={{ fontWeight: r.p * tests < 0.05 ? 700 : 400 }}>{r.p * tests < 0.05 ? "Yes" : "–"}</td>
                      <td className="card-sub">{r.aito ? r.aito.lift.toFixed(1) : "–"}</td>
                      <td className="card-sub">{r.aito?.fOnCondition !== undefined ? `${r.aito.fOnCondition} / ${r.aito.fCondition} / ${r.aito.f} / ${r.aito.n}` : "–"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!all && sorted.length > SHOWN && <div className="card-sub" style={{ marginTop: 4 }}>{sorted.length - SHOWN} more; tick “show all”.</div>}
          </div>
        );
      })}
    </div>
  );
}

export default function Page() {
  return <Suspense fallback={null}><FeedbackPatterns /></Suspense>;
}
