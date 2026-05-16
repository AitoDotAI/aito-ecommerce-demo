"use client";

import { useCallback, useEffect, useState } from "react";

import { apiFetch, fmtEur } from "@/lib/api";
import { recommendationsPanel } from "@/lib/panel-content";
import { usePagePanel, useShell } from "@/components/shell/ShellState";
import ErrorState from "@/components/shell/ErrorState";
import type { ForYouResponse, ForYouTile } from "@/lib/types";


const PERSONAS = [
  { id: "maija", emoji: "🐈", label: "Maija Lehtonen — cat owner" },
  { id: "olli",  emoji: "🐾", label: "Olli Mäkelä — multi-pet (small dog)" },
  { id: "saara", emoji: "🐕", label: "Saara Virtanen — large breed dog owner" },
];


/**
 * For You — personalised tile grid that flips per persona.
 *
 * The grid is driven by `_recommend product_sku from order_lines`
 * with the persona's `customer_pet_size` in `where` and their
 * `customer_segment` in `goal`. Same data, three crisply different
 * shoppers. See `docs/adr/0007-for-you.md`.
 */
export default function ForYouPage() {
  usePagePanel(recommendationsPanel(), {
    title: "For You",
    description:
      "Personalised picks for the selected customer. Same query, same data — " +
      "the grid changes because Aito conditions on the customer's segment.",
    breadcrumb: "For You",
  });

  const { setPanel } = useShell();
  const [persona, setPersona] = useState("maija");
  const [data, setData] = useState<ForYouResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchTiles = useCallback(async (p: string) => {
    setLoading(true);
    setError(null);
    setData(null);   // see B1 fix in bought-together/page.tsx
    try {
      const res = await apiFetch<ForYouResponse>(`/api/for-you?customer=${p}`);
      setData(res);
      setPanel({
        ...recommendationsPanel(),
        endpoints: ["_recommend"],
        query: highlightQuery(res.last_query.body),
      });
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [setPanel]);

  useEffect(() => {
    fetchTiles(persona);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [persona]);

  return (
    <div className="fade-in">
      <div className="page-header">
        <div className="page-title">For You</div>
        <div className="page-desc">
          Personalised picks for the selected customer. Switch the pill
          to see the entire grid re-rank in under 300 ms — same query
          body, different <code>where</code> + <code>goal</code> context.
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
          >
            <span aria-hidden="true">{p.emoji}</span>
            {p.label}
          </button>
        ))}
        {/* Latency pill moved to the TopBar — see LatencyBadge. */}
      </div>

      {error && (
        <ErrorState
          title="Couldn't load For You"
          message={`Aito returned an error. ${error}`}
          command="./do load-data"
        />
      )}

      {!error && (
        <>
          <div className="card-sub" style={{ marginBottom: 12 }}>
            {data ? (
              <>
                <strong>{data.persona.label}</strong> · {data.tiles.length} picks
                <span style={{ color: "var(--text-muted)", marginLeft: 8 }}>
                  · goal{" "}
                  <code style={{ fontFamily: "var(--mono)" }}>
                    {`{segment: ${data.persona.segment}${
                      data.persona.pet_size ? `, pet_size: ${data.persona.pet_size}` : ""
                    }}`}
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
          <span className="rec-card-score" title="P(segment | product)">
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


// ── Panel query body pretty-printer ───────────────────────────────


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
