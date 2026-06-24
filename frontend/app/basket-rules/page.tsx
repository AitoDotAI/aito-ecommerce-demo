"use client";

import { useCallback, useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";
import { basketRulesPanel } from "@/lib/panel-content";
import { usePagePanel, useShell } from "@/components/shell/ShellState";
import LiftHint from "@/components/prediction/LiftHint";
import ErrorState from "@/components/shell/ErrorState";
import type { BasketRulesResponse, BasketRule } from "@/lib/types";


/**
 * Basket Rules — association-rule mining as a live query.
 *
 * Data layer: `src/basket_rules_service.py`. Sweeps a set of anchors
 * with the order-level `_relate` (the Bought Together shape) and ranks
 * the resulting `A → B` rules by lift. Confidence, support, and lift
 * come straight from Aito's `fs` — no Python rule computation, no
 * Apriori batch job. See ADR 0022.
 */
export default function BasketRulesPage() {
  usePagePanel(basketRulesPanel(), {
    title: "Basket Rules",
    description:
      "Association-rule mining across the catalogue — the strongest " +
      "“customers who buy A also buy B” rules, ranked by lift, computed " +
      "live by _relate.",
    breadcrumb: "Basket Rules",
  });

  const { setPanel } = useShell();
  const [data, setData] = useState<BasketRulesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch<BasketRulesResponse>("/api/basket-rules");
      setData(res);
      setPanel({
        ...basketRulesPanel(),
        endpoints: ["_relate"],
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="fade-in">
      <div className="page-header">
        <div className="page-title">Basket Rules</div>
        <div className="page-desc">
          Market-basket analysis as a live query. Each row is an{" "}
          <code>A → B</code> rule mined by one <code>_relate</code> per
          anchor — <strong>no precomputed rule table, no Apriori batch</strong>.
          Rules are directional: 94% of dental-treat baskets also hold dog
          dry-food, but only 72% the other way.
        </div>
      </div>

      {error && (
        <ErrorState
          title="Couldn't load Basket Rules"
          message={`Aito returned an error. ${error}`}
          command="./do load-data"
        />
      )}

      {!error && (
        <>
          {data && (
            <div className="card-sub" style={{ marginBottom: 12 }}>
              Mined <strong>{data.anchors_mined}</strong> anchors over{" "}
              <strong>{data.total_orders.toLocaleString("fi-FI")}</strong>{" "}
              orders — {data.rules.length} rules above the lift &amp;
              support gate.
            </div>
          )}

          <div className="card" style={{ padding: 0, overflow: "hidden" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ background: "var(--bg)", textAlign: "left" }}>
                  <Th>If the basket has…</Th>
                  <Th>…it also has</Th>
                  <Th align="right">Confidence</Th>
                  <Th align="right">Lift</Th>
                  <Th align="right">Support</Th>
                </tr>
              </thead>
              <tbody>
                {loading &&
                  Array.from({ length: 10 }).map((_, i) => <RuleSkeleton key={i} />)}
                {!loading &&
                  data?.rules.map((r, i) => <RuleRow key={i} r={r} />)}
                {!loading && data && data.rules.length === 0 && (
                  <tr>
                    <td colSpan={5} data-empty-state style={{ padding: 24, color: "var(--text-muted)" }}>
                      No rules cleared the lift + support gate.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}


// ── Cells ──────────────────────────────────────────────────────────


function Th({ children, align }: { children: React.ReactNode; align?: "right" }) {
  return (
    <th
      style={{
        padding: "10px 14px",
        fontSize: 11,
        fontWeight: 600,
        color: "var(--text-muted)",
        textTransform: "uppercase",
        letterSpacing: "0.04em",
        textAlign: align ?? "left",
        borderBottom: "1px solid var(--border)",
      }}
    >
      {children}
    </th>
  );
}


function RuleRow({ r }: { r: BasketRule }) {
  return (
    <tr style={{ borderBottom: "1px solid var(--border-light)" }}>
      <td style={{ padding: "10px 14px", fontWeight: 600 }}>{r.antecedent}</td>
      <td style={{ padding: "10px 14px" }}>
        <span style={{ color: "var(--text-muted)" }}>→ </span>
        <span style={{ fontWeight: 600 }}>{r.consequent}</span>
      </td>
      <td style={{ padding: "10px 14px", textAlign: "right" }}>
        <ConfidenceBar value={r.confidence} />
      </td>
      <td style={{ padding: "10px 14px", textAlign: "right" }}>
        <LiftHint value={r.lift} />
      </td>
      <td
        style={{
          padding: "10px 14px",
          textAlign: "right",
          color: "var(--text-muted)",
          fontFamily: "var(--mono)",
          fontSize: 12,
        }}
        title={`${r.support_orders.toLocaleString("fi-FI")} orders`}
      >
        {(r.support_pct * 100).toFixed(0)}%
      </td>
    </tr>
  );
}


function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  return (
    <div style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
      <div
        style={{
          width: 64,
          height: 6,
          borderRadius: 3,
          background: "var(--border-light)",
          overflow: "hidden",
        }}
        aria-hidden="true"
      >
        <div style={{ width: `${pct}%`, height: "100%", background: "var(--cta)" }} />
      </div>
      <span style={{ fontWeight: 600, minWidth: 32, display: "inline-block" }}>{pct}%</span>
    </div>
  );
}


function RuleSkeleton() {
  return (
    <tr style={{ borderBottom: "1px solid var(--border-light)" }}>
      {Array.from({ length: 5 }).map((_, i) => (
        <td key={i} style={{ padding: "10px 14px" }}>
          <div style={{ height: 12, background: "var(--border-light)", borderRadius: 3 }} />
        </td>
      ))}
    </tr>
  );
}


// ── Panel query body pretty-printer (mirrors other views) ─────────


function highlightQuery(body: Record<string, unknown>): string {
  function fmt(value: unknown, indent: number): string {
    const pad = "  ".repeat(indent);
    if (value === null) return `<span class="s">null</span>`;
    if (typeof value === "string") return `<span class="s">"${escape(value)}"</span>`;
    if (typeof value === "boolean" || typeof value === "number")
      return `<span class="n">${value}</span>`;
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
