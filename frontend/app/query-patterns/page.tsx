"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";

import { apiFetch, fmtEur } from "@/lib/api";
import { highlightQuery } from "@/lib/highlight-query";
import { recommendMinimalPanel } from "@/lib/panel-content";
import { usePagePanel, useShell } from "@/components/shell/ShellState";
import ErrorState from "@/components/shell/ErrorState";
import type { ForYouResponse, ForYouTile } from "@/lib/types";
import { useUrlState } from "@/lib/use-url-state";


const PERSONAS = [
  { id: "maija", emoji: "🐈", label: "Maija Lehtonen — cat owner" },
  { id: "olli",  emoji: "🐾", label: "Olli Mäkelä — multi-pet (small dog)" },
  { id: "saara", emoji: "🐕", label: "Saara Virtanen — large breed dog owner" },
];


/**
 * Query patterns (ADR 0041): one minimal, runnable call per Aito endpoint,
 * each pointing to the view that sends it in its production form.
 *
 * The first is `_recommend` (called For You before): `product_sku` from
 * `impressions`, with only the customer in `where` and the goal
 * `{purchased: true}`. Aito learns each customer from their own rows. The
 * body shown is the one the backend sent (`src/recommend_service.py`).
 */
function QueryPatternsView() {
  usePagePanel(recommendMinimalPanel(), {
    title: "Query patterns",
    description: "One minimal, runnable call per Aito endpoint.",
    breadcrumb: "Query patterns",
  });

  const { setPanel } = useShell();
  const [persona, setPersona] = useUrlState("customer", "maija");
  const [data, setData] = useState<ForYouResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchTiles = useCallback(async (p: string) => {
    setLoading(true);
    setError(null);
    setData(null);   // the previous customer's grid must not show under the new one
    try {
      const res = await apiFetch<ForYouResponse>(`/api/for-you?customer=${p}`);
      setData(res);
      setPanel({ ...recommendMinimalPanel(), query: highlightQuery(res.last_query.body) });
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [setPanel]);

  useEffect(() => {
    fetchTiles(persona);
  }, [fetchTiles, persona]);

  return (
    <div className="fade-in">
      <div className="page-header">
        <div className="page-title">Query patterns</div>
        <div className="page-desc">
          The smallest call that works, per Aito endpoint, run live against this shop&apos;s data. Each
          names the view that sends the fuller form a shop would ship.
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-title">
          <code>_recommend</code>: the minimal form
        </div>
        <div className="card-sub" style={{ lineHeight: 1.6, marginBottom: 12 }}>
          Rank every product by the chance this customer buys it, with nothing but the customer as context.
          Aito learns each customer from their own impression rows: no profile is handed to it. Switch the
          customer and the same body, with one id changed, returns a different grid.
        </div>

        <div className="aito-query" style={{ background: "var(--aito-bg)" }}>
          <pre>
            <span className="p">POST /api/v1/_recommend{"\n"}</span>
            {data
              ? <span dangerouslySetInnerHTML={{ __html: highlightQuery(data.last_query.body) }} />
              : "…"}
          </pre>
        </div>

        <div className="card-sub" style={{ lineHeight: 1.6 }}>
          <strong>Not the Shop&apos;s query.</strong> The{" "}
          <Link href="/shop/">Shop</Link>&apos;s &ldquo;Picked for you&rdquo; sends a fuller{" "}
          <code>_recommend</code> on the same table and goal: the household&apos;s declared pets, the month
          and the cart as context, the household&apos;s diet rule as a filter, and no customer id. In a
          held-out comparison (ADR 0033), adding the id to that form found no more of what shoppers bought
          and made its probabilities less well calibrated, so the Shop leaves it out.
        </div>
      </div>

      <div className="search-wrap" style={{ flexWrap: "wrap" }}>
        {PERSONAS.map((p) => (
          <button
            key={p.id}
            type="button"
            className={`customer-chip${persona === p.id ? " selected" : ""}`}
            onClick={() => setPersona(p.id)}
          >
            <span aria-hidden="true">{p.emoji}</span>
            {p.label}
          </button>
        ))}
      </div>

      {error && (
        <ErrorState
          title="Couldn't run the _recommend example"
          message={`Aito returned an error. ${error}`}
          command="./do load-data"
        />
      )}

      {!error && (
        <>
          <div className="card-sub" style={{ marginBottom: 12 }}>
            {data ? (
              <>
                <strong>{data.persona.label}</strong> · top {data.tiles.length}
                <span style={{ color: "var(--text-muted)", marginLeft: 8 }}>
                  · where{" "}
                  <code style={{ fontFamily: "var(--mono)" }}>
                    {`{context.customer: ${data.persona.customer_id}}`}
                  </code>
                </span>
              </>
            ) : (
              "Loading…"
            )}
          </div>

          <div className="rec-grid">
            {loading && Array.from({ length: 8 }).map((_, i) => <TileSkeleton key={i} />)}
            {!loading && data?.tiles.map((t) => <Tile key={t.sku} tile={t} />)}
          </div>
        </>
      )}
    </div>
  );
}


function Tile({ tile }: { tile: ForYouTile }) {
  const petEmoji =
    tile.pet_type === "dog"   ? "🐕" :
    tile.pet_type === "cat"   ? "🐈" :
    tile.pet_type === "small_animal" ? "🐹" :
    tile.pet_type === "bird"  ? "🐦" :
    tile.pet_type === "aquarium" ? "🐟" : "🛒";

  return (
    <div className="rec-card">
      <div className="rec-card-img" aria-hidden="true">{petEmoji}</div>
      <div className="rec-card-body">
        <div className="rec-card-name">{tile.name}</div>
        <div className="rec-card-brand">{tile.brand} · {tile.category}</div>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 4 }}>
          <span className="rec-card-price">{fmtEur(tile.price_eur)}</span>
          <span className="rec-card-score" title="P(purchased | this customer), from Aito's $p">
            p {tile.score.toFixed(2)}
          </span>
        </div>
      </div>
    </div>
  );
}


function TileSkeleton() {
  return (
    <div className="rec-card" style={{ minHeight: 160 }}>
      <div className="rec-card-img" style={{ background: "var(--border-light)" }} />
      <div className="rec-card-body">
        <div style={{ height: 12, background: "var(--border-light)", borderRadius: 3, marginBottom: 8 }} />
        <div style={{ height: 9, background: "var(--border-light)", borderRadius: 3, width: "70%" }} />
      </div>
    </div>
  );
}


// The view reads its state from the URL (`useUrlState`), which the static
// export only allows under a Suspense boundary.
export default function QueryPatternsPage() {
  return (
    <Suspense>
      <QueryPatternsView />
    </Suspense>
  );
}
