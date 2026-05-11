"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { apiFetch, fmtEur } from "@/lib/api";
import { smartSearchPanel } from "@/lib/panel-content";
import { usePagePanel, useShell } from "@/components/shell/ShellState";
import ErrorState from "@/components/shell/ErrorState";
import type {
  SmartSearchHit,
  SmartSearchHitWithDelta,
  SmartSearchResponse,
} from "@/lib/types";

const PERSONAS: Array<{ id: string; emoji: string; label: string; segment: string; pet_size?: string }> = [
  { id: "maija", emoji: "🐈", label: "Maija — cat owner",            segment: "cat_owner" },
  { id: "olli",  emoji: "🐾", label: "Olli — multi-pet (small dog)",  segment: "multi_pet", pet_size: "small" },
  { id: "saara", emoji: "🐕", label: "Saara — dog owner (large breed)", segment: "dog_owner", pet_size: "large" },
];


export default function SmartSearchPage() {
  usePagePanel(smartSearchPanel(), {
    title: "Smart Search",
    description:
      "Same query, side-by-side results — left is plain token match, " +
      "right is Aito's prediction conditioned on the customer's segment.",
    breadcrumb: "Smart Search",
  });

  const { setPanel } = useShell();
  const [persona, setPersona] = useState("saara");
  const [query, setQuery] = useState("food");
  const [data, setData] = useState<SmartSearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchSearch = useCallback(async (q: string, p: string) => {
    setLoading(true);
    setError(null);
    setData(null);   // see B1 fix in bought-together/page.tsx
    try {
      const res = await apiFetch<SmartSearchResponse>(
        `/api/smart-search?q=${encodeURIComponent(q)}&customer=${p}`,
      );
      setData(res);
      // Update the Aito panel's query block with the *actual* body
      // that ran. The default `smartSearchPanel()` shows the
      // `_search` baseline; once a search runs we want the
      // `_recommend` body (with the live segment + pet_size) on
      // screen because that's the predictive call.
      setPanel({
        ...smartSearchPanel(),
        endpoints: ["_search", "_recommend"],
        query: highlightQuery(res.last_query.body),
      });
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [setPanel]);

  useEffect(() => {
    fetchSearch(query, persona);
    // Run on mount + when persona changes. Query changes go through
    // the search-button handler so the user controls typing pace.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [persona]);

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    fetchSearch(query, persona);
  };

  return (
    <div className="fade-in">
      <div className="page-header">
        <div className="page-title">Smart Search</div>
        <div className="page-desc">
          Same query, side-by-side. Left is plain token match; right is
          Aito's prediction conditioned on the customer's segment. Flip
          the customer pill to see the predictive column re-rank live.
        </div>
      </div>

      {/* Persona pill bar */}
      <div className="search-wrap" style={{ flexWrap: "wrap" }}>
        {PERSONAS.map((p) => (
          <button
            key={p.id}
            type="button"
            className={`customer-chip${persona === p.id ? " selected" : ""}`}
            onClick={() => setPersona(p.id)}
            style={{ border: "1px solid var(--border)" }}
          >
            <span aria-hidden="true">{p.emoji}</span>
            {p.label}
          </button>
        ))}
      </div>

      {/* Search bar */}
      <form className="search-wrap" onSubmit={onSubmit}>
        <div className="search-input-wrap">
          <span className="search-icon" aria-hidden="true">🔍</span>
          <input
            className="search-input"
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search products..."
          />
        </div>
        <button type="submit" className="btn btn-primary">
          {loading ? "Searching…" : "Search"}
        </button>
      </form>

      {error && (
        <ErrorState
          title="Couldn't run Smart Search"
          message={`Aito returned an error. ${error}`}
          command="./do load-data"
        />
      )}

      {!error && (
        <div className="two-col">
          <ResultsColumn
            title="Standard search"
            sub="Plain token match on the product name."
            hits={data?.baseline ?? []}
            loading={loading || !data}
          />
          <PredictiveColumn
            title="Predictive search"
            sub={
              data
                ? `Re-ranked for ${data.customer.label} — same query, customer-context bias.`
                : "Re-ranked by Aito's prediction…"
            }
            hits={data?.predictive ?? []}
            loading={loading || !data}
          />
        </div>
      )}
    </div>
  );
}


// ── Columns ────────────────────────────────────────────────────────


function ResultsColumn({
  title,
  sub,
  hits,
  loading,
}: {
  title: string;
  sub: string;
  hits: SmartSearchHit[];
  loading: boolean;
}) {
  return (
    <div className="card">
      <div className="card-title" style={{ marginBottom: 4 }}>{title}</div>
      <div className="card-sub" style={{ fontFamily: "var(--mono)", fontSize: 11 }}>{sub}</div>
      <div style={{ marginTop: 12 }}>
        {loading && <SkeletonRows count={10} />}
        {!loading && hits.length === 0 && (
          <div style={{ fontSize: 13, color: "var(--text-muted)", padding: 12 }}>
            No matches.
          </div>
        )}
        {!loading && hits.map((h) => <ResultRow key={h.sku} hit={h} />)}
      </div>
    </div>
  );
}


function PredictiveColumn({
  title,
  sub,
  hits,
  loading,
}: {
  title: string;
  sub: string;
  hits: SmartSearchHitWithDelta[];
  loading: boolean;
}) {
  return (
    <div className="card">
      <div className="card-title" style={{ marginBottom: 4 }}>{title}</div>
      <div className="card-sub" style={{ fontFamily: "var(--mono)", fontSize: 11 }}>{sub}</div>
      <div style={{ marginTop: 12 }}>
        {loading && <SkeletonRows count={10} />}
        {!loading && hits.map((h) => <ResultRow key={h.sku} hit={h} delta />)}
      </div>
    </div>
  );
}


function ResultRow({
  hit,
  delta,
}: {
  hit: SmartSearchHit | SmartSearchHitWithDelta;
  delta?: boolean;
}) {
  const petTone = hit.pet_type === "dog" ? "orange"
    : hit.pet_type === "cat" ? "blue"
    : hit.pet_type === "aquarium" ? "purple"
    : "grey";

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "26px 1fr auto auto",
        gap: 10,
        alignItems: "center",
        padding: "8px 0",
        borderBottom: "1px solid var(--border-light)",
      }}
    >
      <span
        style={{
          fontFamily: "var(--mono)",
          fontSize: 11,
          color: "var(--text-muted)",
          width: 24,
          textAlign: "right",
        }}
      >
        {hit.rank}.
      </span>
      <div>
        <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text)" }}>
          {hit.name}
        </div>
        <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
          <span className={`pill pill-${petTone}`} style={{ marginRight: 6 }}>
            {hit.pet_type}
          </span>
          {hit.brand} · {hit.category}
        </div>
      </div>
      <span style={{ fontSize: 13, fontWeight: 600 }}>{fmtEur(hit.price_eur)}</span>
      {delta && <DeltaChip hit={hit as SmartSearchHitWithDelta} />}
    </div>
  );
}


function DeltaChip({ hit }: { hit: SmartSearchHitWithDelta }) {
  if (hit.new_entry) {
    return (
      <span
        className="lift-hint up"
        style={{ background: "var(--cta-bg)", color: "var(--cta)" }}
        title="Not in baseline top-10"
      >
        ★ new
      </span>
    );
  }
  if (hit.delta_rank == null || hit.delta_rank === 0) {
    return <span className="lift-hint neutral">—</span>;
  }
  if (hit.delta_rank < 0) {
    return (
      <span className="lift-hint up" title={`Moved up ${-hit.delta_rank} positions`}>
        ↑ {-hit.delta_rank}
      </span>
    );
  }
  return (
    <span className="lift-hint down" title={`Moved down ${hit.delta_rank} positions`}>
      ↓ {hit.delta_rank}
    </span>
  );
}


function SkeletonRows({ count }: { count: number }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          style={{
            height: 36,
            background: "var(--border-light)",
            borderRadius: 4,
            opacity: 0.5,
          }}
        />
      ))}
    </div>
  );
}


// ── Aito-panel query body pretty-printer ──────────────────────────


function highlightQuery(body: Record<string, unknown>): string {
  // Render the body as a syntax-highlighted JSON block matching
  // `.aito-query .k|.n|.s|.p` classes in globals.css.
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
