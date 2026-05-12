"use client";

import { useCallback, useEffect, useState } from "react";

import { apiFetch, fmtEur } from "@/lib/api";
import { churnPanel } from "@/lib/panel-content";
import { usePagePanel, useShell } from "@/components/shell/ShellState";
import ErrorState from "@/components/shell/ErrorState";
import type { ChurnResponse, ChurnAtRiskCustomer, ChurnDriverRow } from "@/lib/types";


/**
 * Churn — the killer feature of the Understand section. KPI strip
 * over `_search`-counted totals, at-risk leaderboard from N parallel
 * `_predict churned` calls, drivers from three parallel `_relate`
 * calls, honest accuracy from one `_evaluate`. See
 * `docs/adr/0013-churn-prediction.md`.
 */
export default function ChurnPage() {
  usePagePanel(churnPanel(), {
    title: "Churn",
    description:
      "Per-customer `_predict churned` ranks active customers by risk. " +
      "Drivers via parallel `_relate`. Honest accuracy via `_evaluate` " +
      "with the timestamp held out — Aito predicts churn from who they " +
      "are, not from when they last ordered.",
    breadcrumb: "Churn",
  });

  const { setPanel } = useShell();
  const [data, setData] = useState<ChurnResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    setData(null);
    try {
      const res = await apiFetch<ChurnResponse>("/api/churn");
      setData(res);
      setPanel({
        ...churnPanel(),
        endpoints: ["_predict", "_relate", "_evaluate"],
        query: highlightQuery(res.last_query.body),
      });
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [setPanel]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return (
    <div className="fade-in">
      <div className="page-header">
        <div className="page-title">Churn</div>
        <div className="page-desc">
          Active customers ranked by P(churned). Drivers from
          <code> _relate churned=true</code>. Honest accuracy from
          <code> _evaluate</code> with the timestamp held out.
        </div>
      </div>

      {error && (
        <ErrorState
          title="Couldn't load Churn"
          message={`Aito returned an error. ${error}`}
          command="./do load-data"
        />
      )}

      {/* KPI strip */}
      {data && (
        <div className="kpi-grid" style={{ marginBottom: 20 }}>
          {data.kpis.map((k) => (
            <div className="card kpi-card" key={k.label}>
              <div className="kpi-label">{k.label}</div>
              <div className="kpi-val">
                {typeof k.value === "number" && k.label.includes("rate")
                  ? `${k.value}%`
                  : k.value.toLocaleString()}
              </div>
              <div className="kpi-sub">{k.sub}</div>
            </div>
          ))}
        </div>
      )}
      {(loading || !data) && !error && (
        <div className="kpi-grid" style={{ marginBottom: 20 }}>
          {[1, 2, 3, 4].map((i) => (
            <div className="card kpi-card" key={i}>
              <div style={{ height: 60, background: "var(--border-light)", borderRadius: 4 }} />
            </div>
          ))}
        </div>
      )}

      {/* At-risk leaderboard | Drivers + Eval */}
      {!error && (
        <div className="two-col">
          {/* At-risk leaderboard */}
          <div className="card">
            <div className="card-sub" style={{ marginBottom: 6 }}>
              At-risk leaderboard · top 20 active customers by P(churn)
            </div>
            <div className="page-title" style={{ fontSize: 17, margin: "4px 0 12px" }}>
              Most likely to churn
            </div>

            {(loading || !data) && (
              <div style={{ height: 480, background: "var(--border-light)", borderRadius: 4 }} />
            )}
            {!loading && data && (
              <div style={{ overflowX: "auto" }}>
                <table className="recent-table" style={{ width: "100%", fontSize: 12.5 }}>
                  <thead>
                    <tr>
                      <th style={{ textAlign: "left" }}>Customer</th>
                      <th style={{ textAlign: "left" }}>Segment</th>
                      <th style={{ textAlign: "left" }}>Region</th>
                      <th style={{ textAlign: "right" }}>Orders</th>
                      <th style={{ textAlign: "right" }}>LTV</th>
                      <th style={{ textAlign: "right" }}>Risk</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.at_risk.map((c) => (
                      <AtRiskRow key={c.customer_id} c={c} />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Drivers + Evaluation */}
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {/* Drivers */}
            <div className="card">
              <div className="card-sub" style={{ marginBottom: 6 }}>
                Drivers · `_relate` × 3 over churned subset
              </div>
              <div className="page-title" style={{ fontSize: 17, margin: "4px 0 12px" }}>
                What predicts churn
              </div>

              {(loading || !data) && (
                <div style={{ height: 180, background: "var(--border-light)", borderRadius: 4 }} />
              )}
              {!loading && data && data.drivers.length === 0 && (
                <div className="card-sub">No strong drivers found.</div>
              )}
              {!loading && data?.drivers.map((d, i) => (
                <DriverChip key={`${d.field}-${d.value}-${i}`} d={d} />
              ))}
            </div>

            {/* Evaluation */}
            <div className="card" style={{ borderTop: "3px solid var(--cta)" }}>
              <div className="card-sub" style={{ marginBottom: 6 }}>
                Held-out accuracy · `_evaluate churned`
              </div>
              <div className="page-title" style={{ fontSize: 17, margin: "4px 0 12px" }}>
                {data && (
                  <>
                    {Math.round(data.evaluation.accuracy * 100)}%
                    <span style={{
                      marginLeft: 10, fontSize: 13, fontWeight: 500,
                      color: data.evaluation.accuracy_gain_pp >= 10 ? "var(--green)" : "var(--red)",
                    }}>
                      {data.evaluation.accuracy_gain_pp >= 0 ? "+" : ""}
                      {data.evaluation.accuracy_gain_pp.toFixed(1)} pp vs baseline
                    </span>
                  </>
                )}
                {!data && "—"}
              </div>
              {data && (
                <div className="card-sub" style={{ lineHeight: 1.6 }}>
                  Baseline accuracy <strong>{Math.round(data.evaluation.base_accuracy * 100)}%</strong>
                  {" "}(always-predict-majority).
                  Tested on <strong>{data.evaluation.n}</strong> held-out customers.
                  Timestamp held out so Aito can't leak the label.
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


// ── Small UI helpers ──────────────────────────────────────────────


function AtRiskRow({ c }: { c: ChurnAtRiskCustomer }) {
  const bg =
    c.confidence_band === "high"   ? "var(--red-bg)" :
    c.confidence_band === "medium" ? "var(--cta-bg)" :
                                     "var(--bg)";
  const fg =
    c.confidence_band === "high"   ? "var(--red)" :
    c.confidence_band === "medium" ? "var(--cta)" :
                                     "var(--text-muted)";
  return (
    <tr>
      <td>
        <strong>{c.customer_short}</strong>
        {c.last_order_month && (
          <span style={{ marginLeft: 6, color: "var(--text-muted)", fontSize: 11 }}>
            last: {c.last_order_month}
          </span>
        )}
      </td>
      <td>
        <span style={{ color: "var(--text-muted)" }}>{c.segment.replace("_", " ")}</span>
        {c.pet_size && <span style={{ marginLeft: 4, fontSize: 11 }}>· {c.pet_size}</span>}
      </td>
      <td>{c.region}</td>
      <td style={{ textAlign: "right" }}>{c.total_orders}</td>
      <td style={{ textAlign: "right" }}>{fmtEur(c.total_spent_eur)}</td>
      <td style={{ textAlign: "right" }}>
        <span
          className="pill"
          style={{
            background: bg, color: fg, fontWeight: 700, fontSize: 11.5,
            padding: "3px 8px", borderRadius: 6,
          }}
          title={`Confidence band: ${c.confidence_band}`}
        >
          {Math.round(c.risk_score * 100)}%
        </span>
      </td>
    </tr>
  );
}


function DriverChip({ d }: { d: ChurnDriverRow }) {
  const up = d.lift >= 1;
  const bg = up ? "var(--red-bg)" : "var(--green-bg)";
  const fg = up ? "var(--red)"    : "var(--green)";
  const arrow = up ? "↑" : "↓";
  return (
    <div style={{
      display: "flex", alignItems: "center", justifyContent: "space-between",
      gap: 12, padding: "10px 12px", marginBottom: 6,
      background: bg, borderRadius: 6,
    }}>
      <div>
        <div style={{ fontWeight: 700, fontSize: 13 }}>
          <span style={{ color: "var(--text-muted)", fontWeight: 500 }}>{d.field}</span>
          {" = "}
          <span>{d.value.replace("_", " ")}</span>
        </div>
        <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>
          {Math.round(d.p_churn * 100)}% churn vs {Math.round(d.p_overall * 100)}% baseline
          {" · "}
          {d.support_f} customers
        </div>
      </div>
      <div style={{ fontWeight: 800, fontSize: 14, color: fg }}>
        {arrow} {d.lift.toFixed(2)}×
      </div>
    </div>
  );
}


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
