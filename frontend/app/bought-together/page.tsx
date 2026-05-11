"use client";

import { useCallback, useEffect, useState } from "react";

import { apiFetch, fmtEur } from "@/lib/api";
import { boughtTogetherPanel } from "@/lib/panel-content";
import { usePagePanel, useShell } from "@/components/shell/ShellState";
import LiftHint from "@/components/prediction/LiftHint";
import ErrorState from "@/components/shell/ErrorState";
import type {
  BoughtTogetherResponse,
  BoughtTogetherCrossSell,
  BoughtTogetherSkuSample,
} from "@/lib/types";


/**
 * Bought Together — anchor product on the left, cross-sell tiles
 * on the right with live `_relate` lift scores.
 *
 * Data layer: `src/bought_together_service.py`. Anchor picker is
 * a dropdown over a curated set of (pet, category) pairs; the
 * displayed lift comes straight from Aito's `_relate` response
 * (no Python computation), and the headline 2.72× dog-food →
 * dental-treats moment lands as the top cross-sell of the
 * default anchor.
 */
export default function BoughtTogetherPage() {
  usePagePanel(boughtTogetherPanel(), {
    title: "Bought Together",
    description:
      "Order-level co-occurrence — given an order contains the anchor, " +
      "what other products are most likely to appear in the same basket?",
    breadcrumb: "Bought Together",
  });

  const { setPanel } = useShell();
  const [anchor, setAnchor] = useState("dog_dryfood");
  const [data, setData] = useState<BoughtTogetherResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchData = useCallback(async (a: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch<BoughtTogetherResponse>(
        `/api/bought-together?anchor=${a}`,
      );
      setData(res);
      setPanel({
        ...boughtTogetherPanel(),
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
    fetchData(anchor);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [anchor]);

  return (
    <div className="fade-in">
      <div className="page-header">
        <div className="page-title">Bought Together</div>
        <div className="page-desc">
          Live <code>_relate</code> over <code>orders.line_categories</code>.
          Pick an anchor below and see what else lands in the same basket —
          the headline 2.72× lift is dog dry-food → dental treats.
        </div>
      </div>

      {/* Anchor picker */}
      <div className="search-wrap" style={{ flexWrap: "wrap" }}>
        <label
          htmlFor="anchor-picker"
          style={{ fontSize: 12, fontWeight: 600, color: "var(--text-muted)" }}
        >
          Anchor product
        </label>
        <select
          id="anchor-picker"
          value={anchor}
          onChange={(e) => setAnchor(e.target.value)}
          className="search-input"
          style={{ paddingLeft: 12, width: "auto", minWidth: 220 }}
        >
          {(data?.available_anchors ?? [{ id: anchor, display: "Loading…" }]).map((a) => (
            <option key={a.id} value={a.id}>{a.display}</option>
          ))}
        </select>
        {data && (
          <span
            className="pill pill-grey"
            style={{ marginLeft: "auto", fontFamily: "var(--mono)", fontSize: 11 }}
            title="Last `_relate` round-trip"
          >
            {data.last_response_ms} ms
          </span>
        )}
      </div>

      {error && (
        <ErrorState
          title="Couldn't load Bought Together"
          message={`Aito returned an error. ${error}`}
          command="./do load-data"
        />
      )}

      {!error && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(260px, 1fr) minmax(0, 3fr)",
            gap: 16,
          }}
        >
          <AnchorCard
            display={data?.anchor.display}
            pet_type={data?.anchor.pet_type}
            sample_skus={data?.anchor.sample_skus ?? []}
            loading={loading || !data}
          />

          <div>
            <div className="card-sub" style={{ marginBottom: 10 }}>
              Cross-sells ranked by lift — products most likely to land in the
              same basket as the anchor.
            </div>
            <div className="rec-grid">
              {(loading || !data) && Array.from({ length: 4 }).map((_, i) => (
                <CrossSellSkeleton key={i} />
              ))}
              {!loading && data?.cross_sells.map((c) => (
                <CrossSellTile key={c.token} cs={c} />
              ))}
              {!loading && data && data.cross_sells.length === 0 && (
                <div
                  style={{
                    gridColumn: "1 / -1",
                    padding: 24,
                    background: "var(--bg)",
                    borderRadius: 10,
                    color: "var(--text-muted)",
                    fontSize: 13,
                  }}
                >
                  No cross-sell patterns above the lift threshold. Try
                  another anchor.
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


// ── Tiles ──────────────────────────────────────────────────────────


function AnchorCard({
  display,
  pet_type,
  sample_skus,
  loading,
}: {
  display: string | undefined;
  pet_type: string | undefined;
  sample_skus: BoughtTogetherSkuSample[];
  loading: boolean;
}) {
  const emoji =
    pet_type === "dog"   ? "🐕" :
    pet_type === "cat"   ? "🐈" :
    pet_type === "small_animal" ? "🐹" :
    pet_type === "bird"  ? "🐦" :
    pet_type === "aquarium" ? "🐟" : "🛒";

  return (
    <div className="card" style={{ alignSelf: "start", borderTop: "3px solid var(--cta)" }}>
      <div className="card-sub" style={{ marginBottom: 6 }}>Anchor</div>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
        <span style={{ fontSize: 32 }} aria-hidden="true">{emoji}</span>
        <div className="page-title" style={{ fontSize: 18, margin: 0 }}>
          {display ?? "Loading…"}
        </div>
      </div>

      <div className="card-sub" style={{ marginTop: 12, marginBottom: 4 }}>
        Sample products
      </div>
      {loading && (
        <div style={{ height: 60, background: "var(--border-light)", borderRadius: 4 }} />
      )}
      {!loading && sample_skus.map((s) => (
        <div
          key={s.sku}
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            padding: "6px 0",
            borderBottom: "1px solid var(--border-light)",
            fontSize: 12,
          }}
        >
          <div>
            <div style={{ fontWeight: 600 }}>{s.name}</div>
            <div style={{ color: "var(--text-muted)", fontSize: 11 }}>{s.brand}</div>
          </div>
          <span style={{ fontWeight: 600 }}>{fmtEur(s.price_eur)}</span>
        </div>
      ))}
    </div>
  );
}


function CrossSellTile({ cs }: { cs: BoughtTogetherCrossSell }) {
  return (
    <div className="rec-card">
      <div
        className="rec-card-img"
        aria-hidden="true"
        style={{ background: "var(--cta-bg)" }}
      >
        🛒
      </div>
      <div className="rec-card-body">
        <div
          className="rec-card-name"
          style={{ fontSize: 13, marginBottom: 4 }}
        >
          {cs.label}
        </div>
        <div className="rec-card-brand" style={{ marginBottom: 6 }}>
          {cs.support.f_on_condition.toLocaleString("fi-FI")} of{" "}
          {cs.support.f.toLocaleString("fi-FI")} baskets
        </div>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <LiftHint value={cs.lift} />
          {cs.sample_skus[0] && (
            <span
              style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--text-muted)" }}
              title={cs.sample_skus[0].name}
            >
              e.g. {cs.sample_skus[0].brand}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}


function CrossSellSkeleton() {
  return (
    <div className="rec-card" style={{ minHeight: 140 }}>
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
