"use client";

import { useCallback, useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";
import { demandPanel } from "@/lib/panel-content";
import { usePagePanel, useShell } from "@/components/shell/ShellState";
import WhyPopover from "@/components/prediction/WhyPopover";
import ErrorState from "@/components/shell/ErrorState";
import type { DemandResponse, DemandTopMover, DemandSeasonRow } from "@/lib/types";


/**
 * Demand Forecast — per-SKU `_predict units_sold` for next month
 * + seasonality drivers via parallel `_relate` + honest accuracy
 * via `_evaluate`. See `docs/adr/0014-demand.md`.
 */
export default function DemandPage() {
  usePagePanel(demandPanel(), {
    title: "Demand Forecast",
    description:
      "Per-SKU `_predict units_sold` over the monthly_sales panel " +
      "with seasonality + accuracy on a held-out sample.",
    breadcrumb: "Demand Forecast",
  });

  const { setPanel } = useShell();
  const [data, setData] = useState<DemandResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    setData(null);
    try {
      const res = await apiFetch<DemandResponse>("/api/demand");
      setData(res);
      setPanel({
        ...demandPanel(),
        query: highlightQuery(res.last_query.body),
      });
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [setPanel]);

  useEffect(() => { fetchData(); }, [fetchData]);

  return (
    <div className="fade-in">
      <div className="page-header">
        <div className="page-title">Demand Forecast</div>
        <div className="page-desc">
          Aito predicts next month's units for the top movers,
          surfaces which categories peak in which season via
          <code> _relate</code>, and reports held-out accuracy.
          Forecast month: <code>{data?.forecast_month ?? "—"}</code>.
        </div>
      </div>

      {error && (
        <ErrorState
          title="Couldn't load Demand"
          message={`Aito returned an error. ${error}`}
          command="./do load-data"
        />
      )}

      {!error && (
        <div className="two-col">
          <div className="card">
            <div className="card-sub" style={{ marginBottom: 6 }}>
              Top movers · `_predict units_sold` per SKU
            </div>
            <div className="page-title" style={{ fontSize: 17, margin: "4px 0 12px" }}>
              Highest-volume SKUs
            </div>
            {(loading || !data) && (
              <div style={{ height: 480, background: "var(--border-light)", borderRadius: 4 }} />
            )}
            {!loading && data && (
              <div style={{ overflowX: "auto" }}>
                <table className="recent-table" style={{ width: "100%", fontSize: 12.5 }}>
                  <thead>
                    <tr>
                      <th style={{ textAlign: "left" }}>SKU</th>
                      <th style={{ textAlign: "right" }}>Avg / mo</th>
                      <th style={{ textAlign: "right" }}>Last mo</th>
                      <th style={{ textAlign: "right" }}>Forecast</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.top_movers.map((t) => (
                      <TopMoverRow key={t.sku} t={t} />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div className="card">
              <div className="card-sub" style={{ marginBottom: 6 }}>
                Seasonality · `_relate` × 4 (one per season)
              </div>
              <div className="page-title" style={{ fontSize: 17, margin: "4px 0 12px" }}>
                Which categories peak when
              </div>
              {(loading || !data) && (
                <div style={{ height: 200, background: "var(--border-light)", borderRadius: 4 }} />
              )}
              {!loading && data?.seasonality.map((s, i) => (
                <SeasonChip key={`${s.season}-${s.category}-${i}`} s={s} />
              ))}
              {!loading && data && data.seasonality.length === 0 && (
                <div className="card-sub">No strong seasonal drivers detected.</div>
              )}
            </div>

            <div className="card" style={{ borderTop: "3px solid var(--cta)" }}>
              <div className="card-sub" style={{ marginBottom: 6 }}>
                Accuracy · `_evaluate units_sold`
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
                  Baseline {Math.round(data.evaluation.base_accuracy * 100)}% ·
                  Tested on {data.evaluation.n} held-out monthly_sales rows
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


function TopMoverRow({ t }: { t: DemandTopMover }) {
  return (
    <tr>
      <td>
        <div style={{ fontWeight: 700 }}>{t.name}</div>
        <div style={{ color: "var(--text-muted)", fontSize: 11 }}>
          {t.pet_type} · {t.category}
        </div>
      </td>
      <td style={{ textAlign: "right" }}>{t.avg_monthly_units}</td>
      <td style={{ textAlign: "right" }}>{t.last_month_units}</td>
      <td style={{ textAlign: "right" }}>
        <div style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
          <span className="pill" style={{
            background: "var(--cta-bg)", color: "var(--cta)",
            fontWeight: 700, fontSize: 11.5, padding: "3px 8px", borderRadius: 6,
          }}>
            {t.forecast_units}
          </span>
          {t.why_explanation && (
            <WhyPopover
              why={t.why_explanation}
              title={`${t.name}: ${t.forecast_units} units`}
            />
          )}
        </div>
      </td>
    </tr>
  );
}


function SeasonChip({ s }: { s: DemandSeasonRow }) {
  const up = s.lift >= 1;
  const bg = up ? "var(--red-bg)" : "var(--green-bg)";
  const fg = up ? "var(--red)" : "var(--green)";
  return (
    <div style={{
      display: "flex", alignItems: "center", justifyContent: "space-between",
      gap: 12, padding: "8px 12px", marginBottom: 6,
      background: bg, borderRadius: 6,
    }}>
      <div>
        <div style={{ fontWeight: 700, fontSize: 12.5 }}>
          <span style={{ color: "var(--text-muted)", fontWeight: 500 }}>
            {s.season}
          </span>{" · "}
          <span>{s.category}</span>
        </div>
        <div style={{ fontSize: 10.5, color: "var(--text-muted)" }}>
          {Math.round(s.p_on_condition * 100)}% in season vs {Math.round(s.p_overall * 100)}% baseline
        </div>
      </div>
      <div style={{ fontWeight: 700, fontSize: 13, color: fg }}>
        {up ? "↑" : "↓"} {s.lift.toFixed(2)}×
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
