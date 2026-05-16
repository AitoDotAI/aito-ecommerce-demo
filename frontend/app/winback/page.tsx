"use client";

import { useCallback, useEffect, useState } from "react";

import { apiFetch, fmtEur } from "@/lib/api";
import { winbackPanel } from "@/lib/panel-content";
import { usePagePanel, useShell } from "@/components/shell/ShellState";
import ErrorState from "@/components/shell/ErrorState";
import type {
  WinbackResponse,
  WinbackTarget,
  WinbackProductSuggestion,
  InventoryKpi,
} from "@/lib/types";


/**
 * Win-back Campaigns — for each currently-churned customer, the
 * top-3 products most likely to bring them back. Powered by Aito's
 * `_recommend` over the `winback_campaigns` historical table with
 * goal `responded: true`. See `docs/adr/0020-winback.md`.
 *
 * Ports Netigate accounting-demo's "action + impact estimation"
 * pattern — the empirical-not-simulated revenue impact.
 */
export default function WinbackPage() {
  usePagePanel(winbackPanel(), {
    title: "Win-back",
    description:
      "Churned customers × Aito's `_predict responded` on historical " +
      "re-engagement campaigns = personalised email targets with " +
      "revenue-impact estimation.",
    breadcrumb: "Win-back",
  });

  const { setPanel } = useShell();
  const [data, setData] = useState<WinbackResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    setData(null);
    try {
      const res = await apiFetch<WinbackResponse>("/api/winback");
      setData(res);
      setPanel({
        ...winbackPanel(),
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
        <div className="page-title">Win-back Campaigns</div>
        <div className="page-desc">
          For each currently-churned customer, Aito's <code>_recommend</code> over
          the <code>winback_campaigns</code> historical table — goal{" "}
          <code>{"{responded: true}"}</code> — ranks products by predicted email
          response rate. Multiply by predicted order value and you have €
          recoverable revenue per send.
        </div>
      </div>

      {error && (
        <ErrorState
          title="Couldn't load Win-back"
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
            Re-engagement targets · click a row for the top-3 product suggestions
          </div>
          <div className="page-title" style={{ fontSize: 17, margin: "4px 0 12px" }}>
            {data ? `${data.targets.length} churned customers worth re-engaging` : "Loading…"}
          </div>
          {(loading || !data) && (
            <div style={{ height: 480, background: "var(--border-light)", borderRadius: 4 }} />
          )}
          {!loading && data && (
            <div style={{ overflowX: "auto" }}>
              <table className="recent-table" style={{ width: "100%", fontSize: 12 }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: "left" }}>Customer</th>
                    <th style={{ textAlign: "left" }}>Profile</th>
                    <th style={{ textAlign: "right" }}>Last order</th>
                    <th style={{ textAlign: "right" }}>Lifetime €</th>
                    <th style={{ textAlign: "right" }}>Expected recovery</th>
                  </tr>
                </thead>
                <tbody>
                  {data.targets.map((t) => (
                    <TargetRow
                      key={t.customer_id}
                      t={t}
                      expanded={expanded === t.customer_id}
                      onToggle={() => setExpanded(expanded === t.customer_id ? null : t.customer_id)}
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
  const isCount = k.label === "Targets identified";
  const isRate = k.label === "Average response rate";
  const formatted = isCount
    ? Math.round(k.value).toLocaleString()
    : isRate
      ? `${(k.value * 100).toFixed(0)}%`
      : fmtEur(k.value);
  return (
    <div className="card kpi-card">
      <div className="kpi-label">{k.label}</div>
      <div className="kpi-val">{formatted}</div>
      <div className="kpi-sub">{k.sub}</div>
    </div>
  );
}


function TargetRow({
  t, expanded, onToggle,
}: {
  t: WinbackTarget;
  expanded: boolean;
  onToggle: () => void;
}) {
  const recencyColor = t.recency_bucket === "0-90d"
    ? "var(--green)"
    : t.recency_bucket === "90-180d" ? "var(--cta)" : "var(--red)";
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
          <div style={{ fontWeight: 700, fontSize: 12 }}>{t.customer_name}</div>
          <div style={{ color: "var(--text-muted)", fontSize: 10.5 }}>
            {t.customer_id}
          </div>
        </td>
        <td>
          <span style={{ color: "var(--text-muted)" }}>
            {t.segment.replace("_", " ")}
            {t.pet_size && ` · ${t.pet_size}`}
          </span>
          <div style={{ fontSize: 10.5, color: "var(--text-muted)" }}>
            {t.lifestyle} · {t.health_focus} health
          </div>
        </td>
        <td style={{ textAlign: "right" }}>
          <div>{t.last_order_month}</div>
          <div style={{ fontSize: 10.5, color: recencyColor, fontWeight: 600 }}>
            {t.recency_bucket}
          </div>
        </td>
        <td style={{ textAlign: "right" }}>
          <div style={{ fontWeight: 700 }}>{fmtEur(t.total_spent_eur)}</div>
          <div style={{ fontSize: 10.5, color: "var(--text-muted)" }}>
            {t.total_orders} orders
          </div>
        </td>
        <td style={{ textAlign: "right", fontWeight: 700, color: "var(--cta)" }}>
          {fmtEur(t.expected_recovered_eur)}
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={5} style={{ padding: "12px 16px", background: "var(--bg)" }}>
            <SuggestionsBlock t={t} />
          </td>
        </tr>
      )}
    </>
  );
}


function SuggestionsBlock({ t }: { t: WinbackTarget }) {
  return (
    <div>
      <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 8 }}>
        Top-3 product recommendations for an email send · sorted by predicted response rate
      </div>
      {t.suggestions.length === 0 && (
        <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
          No historical campaigns match this customer's profile — too thin a slice for Aito to predict.
        </div>
      )}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 10 }}>
        {t.suggestions.map((s) => <SuggestionCard key={s.sku} s={s} />)}
      </div>
    </div>
  );
}


function SuggestionCard({ s }: { s: WinbackProductSuggestion }) {
  return (
    <div
      style={{
        border: "1px solid var(--border-light)",
        borderLeft: "3px solid var(--cta)",
        background: "var(--white)",
        borderRadius: 4,
        padding: "10px 12px",
      }}
    >
      <div style={{ fontWeight: 700, fontSize: 12.5 }}>{s.name}</div>
      <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 8 }}>
        {s.brand} · {s.pet_type} · {s.category}
      </div>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 8,
          fontSize: 11,
        }}
      >
        <div>
          <div style={{ color: "var(--text-muted)" }}>Price</div>
          <div style={{ fontWeight: 600, fontSize: 12 }}>{fmtEur(s.price_eur)}</div>
        </div>
        <div>
          <div style={{ color: "var(--text-muted)" }}>Response rate</div>
          <div style={{ fontWeight: 600, fontSize: 12, color: "var(--cta)" }}>
            {(s.response_p * 100).toFixed(0)}%
          </div>
        </div>
        <div>
          <div style={{ color: "var(--text-muted)" }}>Predicted AOV</div>
          <div style={{ fontWeight: 600, fontSize: 12 }}>{fmtEur(s.predicted_aov_eur)}</div>
        </div>
        <div>
          <div style={{ color: "var(--text-muted)" }}>Expected €</div>
          <div style={{ fontWeight: 700, fontSize: 12, color: "var(--cta)" }}>
            {fmtEur(s.expected_revenue_eur)}
          </div>
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
