"use client";

import { Suspense, useCallback, useEffect, useState } from "react";

import { apiFetch, fmtEur } from "@/lib/api";
import { pricePanel } from "@/lib/panel-content";
import { usePagePanel, useShell } from "@/components/shell/ShellState";
import ErrorState from "@/components/shell/ErrorState";
import PriceScatterChart from "@/components/prediction/PriceScatterChart";
import PriceWhatIf from "@/components/prediction/PriceWhatIf";
import DiscountWhatIf from "@/components/prediction/DiscountWhatIf";
import { useSetUrlParams, useUrlState } from "@/lib/use-url-state";
import type {
  PriceResponse, PriceFairBandRow, PriceSweetSpotRow, PriceDetail,
} from "@/lib/types";


/**
 * Price Intelligence — per-SKU fair-band stats from product_states
 * + sweet-spot `_relate` over discount band ↔ category. See
 * `docs/adr/0016-price.md`.
 */
function PriceView() {
  usePagePanel(pricePanel(), {
    title: "Price",
    description:
      "Per-SKU fair-price band from history, a demand curve " +
      "from `_estimate` at seven prices, and a discount what-if from `_predict`.",
    breadcrumb: "Price",
  });

  const { setPanel } = useShell();
  const [data, setData] = useState<PriceResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState<PriceDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  // The SKU and the what-if price live in the URL, so a link opens the same
  // product at the same price. No SKU means the table's first row.
  const [skuParam] = useUrlState("sku", "");
  const [priceParam] = useUrlState("price", "");
  const setUrl = useSetUrlParams();
  const selectedSku = skuParam || data?.fair_bands[0]?.sku || null;
  const setSelectedSku = (sku: string) => setUrl({ sku, price: null });
  const whatIfPrice = priceParam ? Number(priceParam) : null;
  // Commit the SKU with the price, so the link reopens this product even
  // when the page fell back to the table's first row.
  const pickPrice = useCallback(
    (p: number) => { if (selectedSku) setUrl({ sku: selectedSku, price: p.toFixed(2) }); },
    [selectedSku, setUrl],
  );
  const showQuery = useCallback(
    (body: Record<string, unknown>) => setPanel({ ...pricePanel(), query: highlightQuery(body) }),
    [setPanel],
  );
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

  const fetchDetail = useCallback(async (sku: string) => {
    // Clear the previous SKU's chart so the placeholder shows
    // immediately on click instead of the stale chart lingering
    // until the new _estimate returns.
    setDetail(null);
    setDetailError(null);
    try {
      const res = await apiFetch<PriceDetail>(
        `/api/price/detail?sku=${encodeURIComponent(sku)}`,
      );
      setDetail(res);
      // Surface the chart's `_estimate` query body in the Aito panel.
      setPanel({
        ...pricePanel(),
        query: highlightQuery(res.last_query.body),
      });
    } catch (e) {
      setDetailError(String(e));
    }
  }, [setPanel]);

  useEffect(() => { fetchData(); }, [fetchData]);
  useEffect(() => {
    if (selectedSku) fetchDetail(selectedSku);
  }, [selectedSku, fetchDetail]);

  return (
    <div className="fade-in">
      <div className="page-header">
        <div className="page-title">Price</div>
        <div className="page-desc">
          Per-SKU fair-price band (mean ± 1.5σ over product_states)
          with outliers flagged, and each SKU's demand curve: Aito's
          <code>_estimate</code> of next month's units at seven prices.
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

      {/* Price ↔ Demand / Profit scatter chart for the selected SKU.
          Driven by `_estimate units_sold` at ±10 % adjusted prices
          (7-point curve) over the SKU's historical monthly_sales.

          Two-stage render so the title swap on click feels instant:
          the header is driven by the fair-band row (already on the
          client), the chart body waits for `_estimate`. */}
      {!error && (() => {
        const selectedFair = data?.fair_bands.find((f) => f.sku === selectedSku) ?? null;
        const detailMatches = !!detail && detail.sku === selectedSku;
        return (
          <div className="card" style={{ marginBottom: 20, borderTop: "3px solid var(--cta)" }}>
            <div className="card-sub" style={{ marginBottom: 8 }}>
              Demand curve · `_estimate units_sold` × 7 price adjustments
            </div>
            {selectedFair && (
              <div style={{ marginBottom: 10 }}>
                <div style={{ fontWeight: 700, fontSize: 16 }}>{selectedFair.name}</div>
                <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>
                  list €{selectedFair.list_price_eur.toFixed(2)}
                  {detailMatches && ` · cost €${detail.unit_cost_eur.toFixed(2)}`}
                  {" · "}
                  {detailMatches ? detail.historical.length : selectedFair.observation_count} historical months
                </div>
              </div>
            )}
            {!selectedFair && (
              <div style={{ height: 360, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-muted)" }}>
                Click a SKU in the fair-band table to load its demand curve.
              </div>
            )}
            {selectedFair && detailError && (
              <div className="card-sub" style={{ color: "var(--red)" }}>
                Couldn&apos;t estimate the demand curve: {detailError}
              </div>
            )}
            {selectedFair && !detailMatches && !detailError && (
              <div
                aria-busy="true"
                style={{
                  height: 360,
                  background: "var(--border-light)",
                  borderRadius: 4,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  color: "var(--text-muted)",
                  fontSize: 13,
                }}
              >
                Estimating demand curve…
              </div>
            )}
            {selectedFair && detailMatches && <PriceScatterChart detail={detail} onPickPrice={pickPrice} />}
          </div>
        );
      })()}

      {!error && detail && detail.sku === selectedSku && data?.fair_bands.some((f) => f.sku === selectedSku) && (
        <>
          <PriceWhatIf detail={detail} price={whatIfPrice} onPrice={pickPrice} onQuery={showQuery} />
          <DiscountWhatIf sku={detail.sku} onQuery={showQuery} />
        </>
      )}

      {/* The sweet-spots card is shown only when Aito finds a category
          that is discounted more or less than the rest; on today's data
          every lift's interval includes 1 (ADR 0016, 2026-10-11). */}
      {!error && (
        <div className={hasSweetSpots ? "two-col" : undefined}>
          <div className="card">
            <div className="card-sub" style={{ marginBottom: 6 }}>
              Fair-band table · click a row to chart it
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
                      <FairBandRowView
                        key={f.sku}
                        f={f}
                        selected={f.sku === selectedSku}
                        onSelect={() => setSelectedSku(f.sku)}
                      />
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


function FairBandRowView({
  f, selected, onSelect,
}: {
  f: PriceFairBandRow;
  selected: boolean;
  onSelect: () => void;
}) {
  const bg = selected
    ? "rgba(245,166,35,0.12)"
    : f.outlier
      ? "rgba(231,76,60,0.04)"
      : undefined;
  return (
    <tr
      onClick={onSelect}
      style={{
        background: bg,
        cursor: "pointer",
        borderLeft: selected ? "3px solid var(--cta)" : "3px solid transparent",
      }}
    >
      <td>
        <div style={{ fontWeight: 700, fontSize: 12 }}>{f.name}</div>
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


// The view reads its state from the URL (`useUrlState`), which the static
// export only allows under a Suspense boundary.
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
