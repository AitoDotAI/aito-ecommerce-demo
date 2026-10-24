"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { apiFetch, fmtEur } from "@/lib/api";
import { pricePanel } from "@/lib/panel-content";
import { usePagePanel, useShell } from "@/components/shell/ShellState";
import ErrorState from "@/components/shell/ErrorState";
import type { PriceResponse, PriceFairBandRow, PriceSweetSpotRow } from "@/lib/types";


/**
 * Price Intelligence — per-SKU fair-band stats from product_states
 * + sweet-spot `_relate` over discount band ↔ category. See
 * `docs/adr/0016-price.md`. A product's demand curve and what-ifs are on
 * the Product view (ADR 0041); a row opens it.
 */
function PriceView() {
  usePagePanel(pricePanel(), {
    title: "Price",
    description: "Per-SKU fair-price band from history, with outliers flagged.",
    breadcrumb: "Price",
  });

  const { setPanel } = useShell();
  const router = useRouter();
  const [data, setData] = useState<PriceResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // A link to a product's drill-down (`/price/?sku=…&price=…`) now opens
  // the Product view, where the curve and what-ifs moved (ADR 0041).
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.has("sku")) router.replace(`/product/?${params}`);
  }, [router]);
  const hasSweetSpots = !loading && data !== null && data.sweet_spots.length > 0;

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    setData(null);
    try {
      const res = await apiFetch<PriceResponse>("/api/price");
      setData(res);
      setPanel({
        ...pricePanel(),
        query: highlightQuery(res.last_query.body),
      });
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [setPanel]);

  useEffect(() => { fetchData(); }, [fetchData]);

  return (
    <div className="fade-in">
      <div className="page-header">
        <div className="page-title">Price</div>
        <div className="page-desc">
          Per-SKU fair-price band (mean ± 1.5σ over product_states)
          with outliers flagged. Click a product for its demand curve and
          what-ifs, on the Product view.
        </div>
      </div>

      {error && (
        <ErrorState
          title="Couldn't load Price"
          message={`Aito returned an error. ${error}`}
          command="./do load-data"
        />
      )}

      {data && (
        <div className="kpi-grid" style={{ marginBottom: 20 }}>
          <div className="card kpi-card">
            <div className="kpi-label">SKUs tracked</div>
            <div className="kpi-val">{data.summary.total_skus.toLocaleString()}</div>
            <div className="kpi-sub">with ≥ 1 price observation</div>
          </div>
          <div className="card kpi-card">
            <div className="kpi-label">Observations</div>
            <div className="kpi-val">{data.summary.observations.toLocaleString()}</div>
            <div className="kpi-sub">product_states rows</div>
          </div>
          <div className="card kpi-card">
            <div className="kpi-label">Outlier SKUs</div>
            <div className="kpi-val">{data.summary.outlier_skus}</div>
            <div className="kpi-sub">list price outside band</div>
          </div>
          <div className="card kpi-card">
            <div className="kpi-label">Promo share</div>
            <div className="kpi-val">{data.summary.promo_share_pct}%</div>
            <div className="kpi-sub">of observations &gt; 15% off</div>
          </div>
        </div>
      )}

      {/* The sweet-spots card is shown only when Aito finds a category
          that is discounted more or less than the rest; on today's data
          every lift's interval includes 1 (ADR 0016, 2026-10-11). */}
      {!error && (
        <div className={hasSweetSpots ? "two-col" : undefined}>
          <div className="card">
            <div className="card-sub" style={{ marginBottom: 6 }}>
              Fair-band table · a product opens its curve and what-ifs
            </div>
            <div className="page-title" style={{ fontSize: 17, margin: "4px 0 12px" }}>
              Price stats per SKU
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
                      <th style={{ textAlign: "right" }}>List</th>
                      <th style={{ textAlign: "right" }}>Fair band</th>
                      <th style={{ textAlign: "right" }}>Range</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.fair_bands.map((f) => (
                      <FairBandRowView key={f.sku} f={f} />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {hasSweetSpots && (
            <div className="card" style={{ borderTop: "3px solid var(--cta)" }}>
              <div className="card-sub" style={{ marginBottom: 6 }}>
                Sweet spots · `_relate` per discount band
              </div>
              <div className="page-title" style={{ fontSize: 17, margin: "4px 0 12px" }}>
                Which categories over-index at which price
              </div>
              {data.sweet_spots.map((s, i) => (
                <SweetSpotChip key={`${s.discount_band}-${s.category}-${i}`} s={s} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}


function FairBandRowView({ f }: { f: PriceFairBandRow }) {
  return (
    <tr style={{ background: f.outlier ? "rgba(231,76,60,0.04)" : undefined }}>
      <td>
        <Link href={`/product/?sku=${encodeURIComponent(f.sku)}`} style={{ fontWeight: 700, fontSize: 12 }}
              title="Its demand curve and what-ifs, on the Product view">
          {f.name} →
        </Link>
        <div style={{ color: "var(--text-muted)", fontSize: 10.5 }}>
          {f.pet_type} · {f.category}
        </div>
      </td>
      <td style={{ textAlign: "right" }}>
        <span style={{ fontWeight: 700, color: f.outlier ? "var(--red)" : "inherit" }}>
          {fmtEur(f.list_price_eur)}
        </span>
        {f.outlier && (
          <div style={{ fontSize: 10, color: "var(--red)" }}>OUTLIER</div>
        )}
      </td>
      <td style={{ textAlign: "right", fontSize: 11 }}>
        {fmtEur(f.band_lower_eur)}–{fmtEur(f.band_upper_eur)}
        {/* The band is mean ± 1.5σ of these prices: its count says how
            much to trust it (outliers need ≥ 6, ADR 0027 asks for 12). */}
        <div style={{ fontSize: 10, color: "var(--text-muted)" }}>
          from {f.observation_count} prices
        </div>
      </td>
      <td style={{ textAlign: "right", fontSize: 11, color: "var(--text-muted)" }}>
        {fmtEur(f.min_price_eur)} … {fmtEur(f.max_price_eur)}
      </td>
    </tr>
  );
}


function SweetSpotChip({ s }: { s: PriceSweetSpotRow }) {
  const up = s.lift >= 1;
  const bg = up ? "var(--red-bg)" : "var(--green-bg)";
  const fg = up ? "var(--red)" : "var(--green)";
  const bandLabel: Record<string, string> = {
    list:  "list price (≤ 5% off)",
    mild:  "mild discount (5-15% off)",
    promo: "promo (> 15% off)",
  };
  return (
    <div style={{
      display: "flex", alignItems: "center", justifyContent: "space-between",
      gap: 12, padding: "8px 12px", marginBottom: 6,
      background: bg, borderRadius: 6,
    }}>
      <div>
        <div style={{ fontWeight: 700, fontSize: 12.5 }}>
          <span style={{ color: "var(--text-muted)", fontWeight: 500 }}>
            {bandLabel[s.discount_band] ?? s.discount_band}
          </span>
        </div>
        <div style={{ fontSize: 11, marginTop: 2 }}>
          <strong>{s.category}</strong> · {s.f_on_condition} obs ·
          {Math.round(s.p_on_condition * 100)}% in band vs {Math.round(s.p_overall * 100)}% baseline
        </div>
      </div>
      <div style={{ fontWeight: 700, fontSize: 13, color: fg }}>
        {up ? "↑" : "↓"} {s.lift.toFixed(2)}×
      </div>
    </div>
  );
}


// Kept under a Suspense boundary, as the static export asks of views that
// read the URL.
export default function PricePage() {
  return (
    <Suspense>
      <PriceView />
    </Suspense>
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
