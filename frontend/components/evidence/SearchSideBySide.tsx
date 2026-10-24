"use client";

import { useCallback, useEffect, useState } from "react";

import { apiFetch, fmtEur } from "@/lib/api";
import { highlightQuery } from "@/lib/highlight-query";
import { personalisedSearchPanel } from "@/lib/panel-content";
import { useShell } from "@/components/shell/ShellState";
import ErrorState from "@/components/shell/ErrorState";
import { useUrlState } from "@/lib/use-url-state";
import type {
  SmartSearchHit,
  SmartSearchHitWithDelta,
  SmartSearchResponse,
} from "@/lib/types";

const PERSONAS: Array<{ id: string; emoji: string; label: string }> = [
  { id: "maija", emoji: "🐈", label: "Maija Lehtonen — cat owner" },
  { id: "olli",  emoji: "🐾", label: "Olli Mäkelä — multi-pet (small dog)" },
  { id: "saara", emoji: "🐕", label: "Saara Virtanen — dog owner (large breed)" },
];


/**
 * The live illustration on Personalised search (called Smart Search before):
 * two rankings of the same words, side by side: BM25 alone, and one
 * `_search` that multiplies it by the chance this customer buys, learned
 * from their own rows (the benchmark's "with the shopper's history"). It
 * shows two of the rankings the benchmark compares; it measures nothing.
 * The persona and the submitted words live in the URL.
 */
export default function SearchSideBySide() {
  const { setPanel } = useShell();
  // The persona and the SUBMITTED query live in the URL; typing only edits
  // a draft, so each search (not each keystroke) is a back/forward step.
  const [persona, setPersona] = useUrlState("customer", "saara");
  const [submitted, setSubmitted] = useUrlState("q", "food");
  const [query, setQuery] = useState(submitted);
  useEffect(() => setQuery(submitted), [submitted]);
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
      // that ran: the predictive `_search` (with the customer as
      // context), since that is the call worth reading.
      setPanel({
        ...personalisedSearchPanel(),
        query: highlightQuery(res.last_query.body),
      });
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [setPanel]);

  useEffect(() => {
    fetchSearch(submitted, persona);
  }, [fetchSearch, submitted, persona]);

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (query === submitted) {
      fetchSearch(submitted, persona);   // the same search again: refetch, no new history entry
    } else {
      setSubmitted(query);
    }
  };

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div className="card-title" style={{ marginBottom: 4 }}>See it live: text only, and with the shopper&apos;s history</div>
      <div className="card-sub" style={{ lineHeight: 1.5, marginBottom: 12 }}>
        Two of the rankings below, live for three shoppers. Left: how well the product name matches the words.
        Right: that match multiplied by how likely this customer is to buy, learned from their own history, in a
        single Aito query. An illustration: no number on this card is a measurement.
      </div>
      {/* Persona pill bar */}
      <div className="search-wrap" style={{ flexWrap: "wrap" }}>
        {PERSONAS.map((p) => (
          <button
            key={p.id}
            type="button"
            className={`customer-chip${persona === p.id ? " selected" : ""}`}
            onClick={() => { setQuery(submitted); setPersona(p.id); }}
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
          title="Couldn't run the search"
          message={`Aito returned an error. ${error}`}
          command="./do load-data"
        />
      )}

      {!error && (
        <div className="two-col">
          <ResultsColumn
            title="Text only: BM25"
            sub="Aito's $similarity on the product name, a standard BM25."
            hits={data?.baseline ?? []}
            loading={loading || !data}
          />
          <PredictiveColumn
            title="With this shopper's history"
            sub={
              data
                ? data.text_matched
                  ? `Ranked for ${data.customer.label}: purchase probability × text similarity.`
                  : `No product name matches “${data.query}”. Showing what ${data.customer.label} is most likely to buy instead.`
                : "Ranked by purchase probability × text similarity…"
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
        title="Not in the text-only top 10"
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
