"use client";

import { useCallback, useEffect, useState } from "react";

import { apiFetch, fmtEur } from "@/lib/api";
import { cartCompletionPanel } from "@/lib/panel-content";
import { usePagePanel, useShell } from "@/components/shell/ShellState";
import ErrorState from "@/components/shell/ErrorState";
import type {
  CartCompletionResponse,
  CartScenarioResult,
  AddOnSuggestion,
} from "@/lib/types";


/**
 * Cart Completion — checkout-funnel demo. Four preset carts;
 * each runs an Aito `_relate` over `orders.line_categories`
 * conditioned on the cart's categories, then surfaces a popular
 * product from each top related category. The "what to upsell at
 * checkout" question, answered with the same predictive engine
 * as Bought Together. See `docs/adr/0019-cart-completion.md`.
 */
export default function CartCompletionPage() {
  usePagePanel(cartCompletionPanel(), {
    title: "Cart Completion",
    description:
      "Preset carts × Aito's `_relate` over orders' line_categories " +
      "= one click-to-add suggestion per scenario.",
    breadcrumb: "Cart Completion",
  });

  const { setPanel } = useShell();
  const [data, setData] = useState<CartCompletionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    setData(null);
    try {
      const res = await apiFetch<CartCompletionResponse>("/api/cart-completion");
      setData(res);
      setPanel({
        ...cartCompletionPanel(),
        query: highlightQuery(res.last_query.body),
      });
      if (res.scenarios.length > 0 && !selected) {
        setSelected(res.scenarios[0].scenario_id);
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [setPanel]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const currentScenario = data?.scenarios.find(s => s.scenario_id === selected) ?? null;

  return (
    <div className="fade-in">
      <div className="page-header">
        <div className="page-title">Cart Completion</div>
        <div className="page-desc">
          Each preset cart asks Aito the same question a checkout page asks
          in real time: <em>given what's already in the basket, what's the
          single best add to bump the order value?</em> Powered by{" "}
          <code>_relate</code> over <code>orders.line_categories</code> —
          the same engine as Bought Together.
        </div>
      </div>

      {error && (
        <ErrorState
          title="Couldn't load Cart Completion"
          message={`Aito returned an error. ${error}`}
          command="./do load-data"
        />
      )}

      {/* Scenario selector chips */}
      <div className="search-wrap" style={{ flexWrap: "wrap", marginBottom: 12 }}>
        {data?.scenarios.map(s => (
          <button
            key={s.scenario_id}
            type="button"
            className={`customer-chip${selected === s.scenario_id ? " selected" : ""}`}
            onClick={() => setSelected(s.scenario_id)}
            style={{ border: "1px solid var(--border)" }}
          >
            {s.label}
          </button>
        ))}
        {!data && !error && (
          <span style={{ color: "var(--text-muted)", fontSize: 13 }}>Loading scenarios…</span>
        )}
      </div>

      {currentScenario && (
        <div className="two-col">
          <CartCard scenario={currentScenario} />
          <SuggestionsCard scenario={currentScenario} />
        </div>
      )}

      {(loading || !data) && (
        <div style={{ height: 360, background: "var(--border-light)", borderRadius: 4 }} />
      )}
    </div>
  );
}


function CartCard({ scenario }: { scenario: CartScenarioResult }) {
  return (
    <div className="card">
      <div className="card-sub" style={{ marginBottom: 6 }}>
        In cart
      </div>
      <div className="page-title" style={{ fontSize: 17, margin: "4px 0 12px" }}>
        {scenario.label}
      </div>
      <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 14 }}>
        {scenario.description}
      </div>
      {scenario.items.map(it => (
        <div
          key={it.sku}
          style={{
            display: "grid",
            gridTemplateColumns: "1fr auto",
            gap: 10,
            padding: "10px 0",
            borderBottom: "1px solid var(--border-light)",
          }}
        >
          <div>
            <div style={{ fontSize: 13, fontWeight: 600 }}>{it.name}</div>
            <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{it.category}</div>
          </div>
          <div style={{ fontSize: 13, fontWeight: 600 }}>{fmtEur(it.price_eur)}</div>
        </div>
      ))}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          paddingTop: 12,
          fontSize: 13,
          fontWeight: 700,
        }}
      >
        <span style={{ color: "var(--text-muted)" }}>Cart total</span>
        <span>{fmtEur(scenario.cart_value_eur)}</span>
      </div>
    </div>
  );
}


function SuggestionsCard({ scenario }: { scenario: CartScenarioResult }) {
  const totalUplift = scenario.suggestions.reduce(
    (acc, s) => acc + s.expected_uplift_eur, 0,
  );
  return (
    <div className="card" style={{ borderTop: "3px solid var(--cta)" }}>
      <div className="card-sub" style={{ marginBottom: 6 }}>
        Aito suggests
      </div>
      <div className="page-title" style={{ fontSize: 17, margin: "4px 0 12px" }}>
        {scenario.suggestions.length === 0
          ? "No strong related categories for this cart"
          : `Top ${scenario.suggestions.length} add${scenario.suggestions.length > 1 ? "s" : ""}`}
      </div>
      {scenario.suggestions.length === 0 ? (
        <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
          The <code>_relate</code> call returned no co-occurring categories
          above the 1.15× lift threshold for this cart shape. Genuinely
          uncorrelated baskets — the merchandiser's signal is "this customer
          knows what they want; don't push more".
        </div>
      ) : (
        <>
          {scenario.suggestions.map(s => <SuggestionRow key={s.sku} s={s} />)}
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "baseline",
              paddingTop: 12,
              fontSize: 12.5,
              fontWeight: 700,
              color: "var(--cta)",
            }}
          >
            <span>Expected uplift if all three convert</span>
            <span>{fmtEur(totalUplift)}</span>
          </div>
        </>
      )}
    </div>
  );
}


function SuggestionRow({ s }: { s: AddOnSuggestion }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "1fr auto auto",
        gap: 10,
        alignItems: "center",
        padding: "10px 0",
        borderBottom: "1px solid var(--border-light)",
      }}
    >
      <div>
        <div style={{ fontSize: 13, fontWeight: 600 }}>{s.name}</div>
        <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
          {s.brand} · {s.pet_type} · {s.category}
        </div>
      </div>
      <div style={{ textAlign: "right" }}>
        <div style={{ fontSize: 13, fontWeight: 600 }}>{fmtEur(s.price_eur)}</div>
        <div style={{ fontSize: 11, color: "var(--cta)" }}>
          {(s.attach_p * 100).toFixed(0)}% confidence
        </div>
      </div>
      <div style={{ textAlign: "right" }}>
        <div style={{ fontSize: 11, color: "var(--text-muted)" }}>expected</div>
        <div style={{ fontSize: 13, fontWeight: 700, color: "var(--cta)" }}>
          {fmtEur(s.expected_uplift_eur)}
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
