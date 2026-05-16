"use client";

import { useCallback, useEffect, useState } from "react";

import { apiFetch, fmtEur } from "@/lib/api";
import { markdownPanel } from "@/lib/panel-content";
import { usePagePanel, useShell } from "@/components/shell/ShellState";
import ErrorState from "@/components/shell/ErrorState";
import type {
  MarkdownResponse,
  MarkdownProposal,
  MarkdownCurvePoint,
  InventoryKpi,
} from "@/lib/types";


/**
 * Markdown Decision — for each overstock SKU, Aito's `_estimate
 * units_sold` runs at five price points; the chosen markdown is
 * the one that maximises recoverable revenue while clearing in 3
 * months. Ties Inventory + Price + Demand into one merchandiser
 * workflow. See `docs/adr/0018-markdown.md`.
 */
export default function MarkdownPage() {
  usePagePanel(markdownPanel(), {
    title: "Markdown",
    description:
      "Overstock SKUs × Aito's _estimate at five markdowns = " +
      "proposed discount per SKU + recoverable-revenue roll-up.",
    breadcrumb: "Markdown",
  });

  const { setPanel } = useShell();
  const [data, setData] = useState<MarkdownResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    setData(null);
    try {
      const res = await apiFetch<MarkdownResponse>("/api/markdown");
      setData(res);
      setPanel({
        ...markdownPanel(),
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
        <div className="page-title">Markdown</div>
        <div className="page-desc">
          For each overstock SKU, Aito's <code>_estimate units_sold</code> walks
          the demand curve at five markdowns. The proposed discount maximises
          recoverable revenue while clearing the excess within 3 months.
        </div>
      </div>

      {error && (
        <ErrorState
          title="Couldn't load Markdown"
          message={`Aito returned an error. ${error}`}
          command="./do load-data"
        />
      )}

      {data && (
        <div className="kpi-grid" style={{ marginBottom: 20 }}>
          {data.kpis.map((k) => <KpiCard key={k.label} k={k} />)}
        </div>
      )}

      {!error && (
        <div className="card">
          <div className="card-sub" style={{ marginBottom: 6 }}>
            Proposed markdowns · click a row to see the full curve
          </div>
          <div className="page-title" style={{ fontSize: 17, margin: "4px 0 12px" }}>
            {data ? `${data.proposals.length} overstock SKUs` : "Loading…"}
          </div>
          {(loading || !data) && (
            <div style={{ height: 480, background: "var(--border-light)", borderRadius: 4 }} />
          )}
          {!loading && data && (
            <div style={{ overflowX: "auto" }}>
              <table className="recent-table" style={{ width: "100%", fontSize: 12 }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: "left" }}>SKU</th>
                    <th style={{ textAlign: "right" }}>Stock</th>
                    <th style={{ textAlign: "right" }}>List → markdown</th>
                    <th style={{ textAlign: "right" }}>Clears in</th>
                    <th style={{ textAlign: "right" }}>Recover €</th>
                    <th style={{ textAlign: "right" }}>Margin given up</th>
                  </tr>
                </thead>
                <tbody>
                  {data.proposals.map((p) => (
                    <ProposalRow
                      key={p.sku}
                      p={p}
                      expanded={expanded === p.sku}
                      onToggle={() => setExpanded(expanded === p.sku ? null : p.sku)}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}


function KpiCard({ k }: { k: InventoryKpi }) {
  // "Overstock targeted" is a count; everything else is €. Detect
  // and format accordingly so the unit reads correctly in the UI.
  const isCount = k.label === "Overstock targeted";
  return (
    <div className="card kpi-card">
      <div className="kpi-label">{k.label}</div>
      <div className="kpi-val">
        {isCount ? Math.round(k.value).toLocaleString() : fmtEur(k.value)}
      </div>
      <div className="kpi-sub">{k.sub}</div>
    </div>
  );
}


function ProposalRow({
  p, expanded, onToggle,
}: {
  p: MarkdownProposal;
  expanded: boolean;
  onToggle: () => void;
}) {
  const inHorizon = p.proposed_weeks_to_clear <= 13;  // 3 months ≈ 13 weeks
  const noChange = p.proposed_discount_pct === 0;
  const discountColor = noChange
    ? "var(--text-muted)"
    : inHorizon ? "var(--cta)" : "var(--red)";
  return (
    <>
      <tr
        onClick={onToggle}
        style={{
          cursor: "pointer",
          background: expanded ? "rgba(245,166,35,0.08)" : undefined,
          borderLeft: expanded ? "3px solid var(--cta)" : "3px solid transparent",
        }}
      >
        <td>
          <div style={{ fontWeight: 700, fontSize: 12 }}>{p.name}</div>
          <div style={{ color: "var(--text-muted)", fontSize: 10.5 }}>
            {p.pet_type} · {p.category}
          </div>
        </td>
        <td style={{ textAlign: "right" }}>
          <span style={{ fontWeight: 700 }}>{p.current_stock}</span>
          <div style={{ fontSize: 10.5, color: "var(--text-muted)" }}>
            {p.excess_units} excess · €{p.tied_capital_eur.toFixed(0)} tied
          </div>
        </td>
        <td style={{ textAlign: "right" }}>
          <span style={{ color: "var(--text-muted)", textDecoration: noChange ? "none" : "line-through" }}>
            {fmtEur(p.list_price_eur)}
          </span>
          {!noChange && (
            <>
              {" → "}
              <span style={{ fontWeight: 700, color: discountColor }}>
                {fmtEur(p.proposed_price_eur)}
              </span>
            </>
          )}
          <div style={{ fontSize: 10.5, color: discountColor, fontWeight: 600 }}>
            {noChange
              ? "no discount needed"
              : `${p.proposed_discount_pct}% off`}
          </div>
        </td>
        <td style={{ textAlign: "right" }}>
          <span style={{ fontWeight: 700, color: inHorizon ? "inherit" : "var(--red)" }}>
            {p.proposed_weeks_to_clear.toFixed(1)}w
          </span>
          {!inHorizon && (
            <div style={{ fontSize: 10, color: "var(--red)" }}>
              won't clear in horizon
            </div>
          )}
        </td>
        <td style={{ textAlign: "right", fontWeight: 700 }}>
          {fmtEur(p.proposed_recoverable_revenue_eur)}
        </td>
        <td style={{ textAlign: "right", color: "var(--text-muted)" }}>
          {noChange ? "—" : fmtEur(p.proposed_margin_lost_eur)}
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={6} style={{ padding: "12px 16px", background: "var(--bg)" }}>
            <CurveTable p={p} />
          </td>
        </tr>
      )}
    </>
  );
}


function CurveTable({ p }: { p: MarkdownProposal }) {
  return (
    <div>
      <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 8 }}>
        Aito's <code>_estimate units_sold</code> at each markdown · cost €{p.unit_cost_eur.toFixed(2)} (margin {Math.round((p.list_price_eur - p.unit_cost_eur) / p.list_price_eur * 100)}%)
      </div>
      <table style={{ width: "100%", fontSize: 11.5 }}>
        <thead>
          <tr style={{ color: "var(--text-muted)" }}>
            <th style={{ textAlign: "left", padding: "4px 8px" }}>Discount</th>
            <th style={{ textAlign: "right", padding: "4px 8px" }}>Price</th>
            <th style={{ textAlign: "right", padding: "4px 8px" }}>Monthly units</th>
            <th style={{ textAlign: "right", padding: "4px 8px" }}>Weeks to clear</th>
            <th style={{ textAlign: "right", padding: "4px 8px" }}>Margin / unit</th>
            <th style={{ textAlign: "right", padding: "4px 8px" }}>Recover €</th>
          </tr>
        </thead>
        <tbody>
          {p.curve.map((c) => <CurveRow key={c.discount_pct} c={c} chosen={c.discount_pct === p.proposed_discount_pct} />)}
        </tbody>
      </table>
    </div>
  );
}


function CurveRow({ c, chosen }: { c: MarkdownCurvePoint; chosen: boolean }) {
  return (
    <tr style={{
      background: chosen ? "rgba(245,166,35,0.18)" : undefined,
      fontWeight: chosen ? 700 : 500,
    }}>
      <td style={{ padding: "4px 8px" }}>
        {c.discount_pct === 0 ? "list price" : `−${c.discount_pct}%`}
        {chosen && <span style={{ color: "var(--cta)", marginLeft: 6 }}>← chosen</span>}
      </td>
      <td style={{ padding: "4px 8px", textAlign: "right" }}>{fmtEur(c.price_eur)}</td>
      <td style={{ padding: "4px 8px", textAlign: "right" }}>{c.monthly_units.toFixed(2)}</td>
      <td style={{ padding: "4px 8px", textAlign: "right" }}>
        {c.weeks_to_clear >= 998 ? "—" : c.weeks_to_clear.toFixed(1)}
      </td>
      <td style={{ padding: "4px 8px", textAlign: "right" }}>{fmtEur(c.margin_per_unit_eur)}</td>
      <td style={{ padding: "4px 8px", textAlign: "right" }}>{fmtEur(c.recoverable_revenue_eur)}</td>
    </tr>
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
