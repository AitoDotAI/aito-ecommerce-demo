"use client";

import { useCallback, useEffect, useState } from "react";

import { apiFetch, fmtEur } from "@/lib/api";
import { inventoryPanel } from "@/lib/panel-content";
import { usePagePanel, useShell } from "@/components/shell/ShellState";
import WhyPopover from "@/components/prediction/WhyPopover";
import ErrorState from "@/components/shell/ErrorState";
import type { InventoryResponse, InventoryReorderRow, InventoryOverstockRow } from "@/lib/types";


/**
 * Inventory Intelligence — the killer feature of the Operate
 * section. KPI strip (critical / overstock / tied capital € /
 * revenue at risk €), reorder queue scored by `_predict
 * units_sold` next month, and the top overstock list with tied
 * capital figures. See `docs/adr/0015-inventory.md`.
 */
export default function InventoryPage() {
  usePagePanel(inventoryPanel(), {
    title: "Inventory",
    description:
      "Stock + lead-time × Aito's next-month units forecast = " +
      "reorder workflow. Critical SKUs sort by revenue at risk.",
    breadcrumb: "Inventory",
  });

  const { setPanel } = useShell();
  const [data, setData] = useState<InventoryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    setData(null);
    try {
      const res = await apiFetch<InventoryResponse>("/api/inventory");
      setData(res);
      setPanel({
        ...inventoryPanel(),
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
        <div className="page-title">Inventory</div>
        <div className="page-desc">
          Stock + lead-time arithmetic for every SKU. Critical rows
          ranked by <strong>revenue at risk</strong> from Aito's
          next-month <code>units_sold</code> forecast. Each row's
          <strong> ?</strong> opens the prediction's <code>$why</code>.
        </div>
      </div>

      {error && (
        <ErrorState
          title="Couldn't load Inventory"
          message={`Aito returned an error. ${error}`}
          command="./do load-data"
        />
      )}

      {data && (
        <div className="kpi-grid" style={{ marginBottom: 20 }}>
          {data.kpis.map((k) => (
            <div className="card kpi-card" key={k.label}>
              <div className="kpi-label">{k.label}</div>
              <div className="kpi-val">
                {k.label.includes("capital") || k.label.includes("risk")
                  ? fmtEur(k.value)
                  : Math.round(k.value).toLocaleString()}
              </div>
              <div className="kpi-sub">{k.sub}</div>
            </div>
          ))}
        </div>
      )}
      {(loading || !data) && !error && (
        <div className="kpi-grid" style={{ marginBottom: 20 }}>
          {[1, 2, 3, 4, 5].map((i) => (
            <div className="card kpi-card" key={i}>
              <div style={{ height: 60, background: "var(--border-light)", borderRadius: 4 }} />
            </div>
          ))}
        </div>
      )}

      {!error && (
        <div className="two-col">
          <div className="card">
            <div className="card-sub" style={{ marginBottom: 6 }}>
              Reorder queue · `_predict units_sold` per critical SKU
            </div>
            <div className="page-title" style={{ fontSize: 17, margin: "4px 0 12px" }}>
              Reorder now
            </div>
            {(loading || !data) && (
              <div style={{ height: 480, background: "var(--border-light)", borderRadius: 4 }} />
            )}
            {!loading && data && data.reorder_queue.length === 0 && (
              <div className="card-sub">No critical SKUs — every SKU is above its reorder point.</div>
            )}
            {!loading && data && data.reorder_queue.length > 0 && (
              <div style={{ overflowX: "auto" }}>
                <table className="recent-table" style={{ width: "100%", fontSize: 12.5 }}>
                  <thead>
                    <tr>
                      <th style={{ textAlign: "left" }}>SKU · supplier</th>
                      <th style={{ textAlign: "right" }}>Stock</th>
                      <th style={{ textAlign: "right" }}>Forecast<br/><span style={{ fontSize: 10, fontWeight: 400 }}>next mo.</span></th>
                      <th style={{ textAlign: "right" }}>Order qty</th>
                      <th style={{ textAlign: "right" }}>Rev @ risk</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.reorder_queue.map((r) => (
                      <ReorderRowView key={r.sku} r={r} />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="card" style={{ borderTop: "3px solid var(--cta)" }}>
            <div className="card-sub" style={{ marginBottom: 6 }}>
              Overstock · top tied-capital SKUs
            </div>
            <div className="page-title" style={{ fontSize: 17, margin: "4px 0 12px" }}>
              {data ? `€${Math.round(
                data.overstock.reduce((s, o) => s + o.tied_capital_eur, 0)
              ).toLocaleString()} tied` : "—"}
            </div>
            <div className="card-sub" style={{ marginBottom: 12 }}>
              Stock &gt; 5× reorder point
            </div>
            {(loading || !data) && (
              <div style={{ height: 400, background: "var(--border-light)", borderRadius: 4 }} />
            )}
            {!loading && data?.overstock.map((o) => (
              <OverstockRowView key={o.sku} o={o} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}


function ReorderRowView({ r }: { r: InventoryReorderRow }) {
  return (
    <tr>
      <td>
        <div style={{ fontWeight: 700 }}>{r.name}</div>
        <div style={{ color: "var(--text-muted)", fontSize: 11 }}>
          {r.supplier} · {r.lead_time_days} d lead
        </div>
      </td>
      <td style={{ textAlign: "right" }}>
        <div><strong>{r.current_stock}</strong></div>
        <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
          {r.days_of_supply.toFixed(1)} d supply
        </div>
      </td>
      <td style={{ textAlign: "right" }}>
        <strong>{r.forecast_units}</strong>
        <div style={{ fontSize: 10, color: "var(--text-muted)" }}>
          avg {r.avg_monthly_units}
        </div>
      </td>
      <td style={{ textAlign: "right" }}>
        <span className="pill" style={{
          background: "var(--cta-bg)", color: "var(--cta)",
          fontWeight: 700, fontSize: 11.5, padding: "3px 8px", borderRadius: 6,
        }}>
          {r.suggested_reorder_qty}
        </span>
      </td>
      <td style={{ textAlign: "right" }}>
        <div style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontWeight: 700, color: "var(--red)" }}>
            {fmtEur(r.revenue_at_risk_eur)}
          </span>
          {r.why_explanation && (
            <WhyPopover
              why={r.why_explanation}
              title={`${r.name} forecast = ${r.forecast_units}`}
            />
          )}
        </div>
      </td>
    </tr>
  );
}


function OverstockRowView({ o }: { o: InventoryOverstockRow }) {
  return (
    <div style={{
      display: "flex", justifyContent: "space-between", alignItems: "center",
      padding: "8px 0", borderBottom: "1px solid var(--border-light)",
      gap: 10,
    }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 600, fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {o.name}
        </div>
        <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
          {o.current_stock} units · {o.months_of_supply.toFixed(1)} mo supply
        </div>
      </div>
      <div style={{ textAlign: "right", flexShrink: 0 }}>
        <div style={{ fontWeight: 700, color: "var(--text)" }}>
          {fmtEur(o.tied_capital_eur)}
        </div>
        <div style={{ fontSize: 10, color: "var(--text-muted)" }}>
          @ {fmtEur(o.unit_cost_eur)}/u
        </div>
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
