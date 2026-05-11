"use client";

import { useCallback, useEffect, useState } from "react";

import { apiFetch, confClass, fmtEur } from "@/lib/api";
import { productFillingPanel } from "@/lib/panel-content";
import { usePagePanel, useShell } from "@/components/shell/ShellState";
import WhyTooltip from "@/components/prediction/WhyTooltip";
import ErrorState from "@/components/shell/ErrorState";
import type { FillingResponse, FillingFieldOut } from "@/lib/types";


/**
 * Product Filling — side-by-side incomplete product (left) and
 * Aito-filled five fields (right). Data layer:
 * `src/filling_service.py`; see `docs/adr/0009-product-filling.md`.
 */
export default function ProductFillingPage() {
  usePagePanel(productFillingPanel(), {
    title: "Product Filling",
    description:
      "Multi-field `_predict` over the product name. Five fields, " +
      "one round-trip's worth of work, every prediction with its own " +
      "$why decomposition.",
    breadcrumb: "Product Filling",
  });

  const { setPanel } = useShell();
  const [sku, setSku] = useState<string | undefined>(undefined);
  const [data, setData] = useState<FillingResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchData = useCallback(async (forSku?: string) => {
    setLoading(true);
    setError(null);
    setData(null);   // see B1 fix in bought-together/page.tsx
    try {
      const url = forSku
        ? `/api/product-filling?sku=${encodeURIComponent(forSku)}`
        : "/api/product-filling";
      const res = await apiFetch<FillingResponse>(url);
      setData(res);
      setPanel({
        ...productFillingPanel(),
        endpoints: ["_predict"],
        query: highlightQuery({
          ...res.last_query.body,
          predict: "<dietary | weight_kg | tax_class | pet_type | category>",
        }),
      });
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [setPanel]);

  useEffect(() => {
    fetchData(sku);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sku]);

  return (
    <div className="fade-in">
      <div className="page-header">
        <div className="page-title">Product Filling</div>
        <div className="page-desc">
          Five fields predicted from the product name + brand alone, in
          parallel. Confidence chips and per-field <code>$why</code>
          decompositions come straight from Aito.
        </div>
      </div>

      {/* SKU picker */}
      <div className="search-wrap" style={{ flexWrap: "wrap" }}>
        <label
          htmlFor="sku-picker"
          style={{ fontSize: 12, fontWeight: 600, color: "var(--text-muted)" }}
        >
          Incomplete product
        </label>
        <select
          id="sku-picker"
          className="search-input"
          style={{ paddingLeft: 12, width: "auto", minWidth: 360 }}
          value={sku ?? data?.product.sku ?? ""}
          onChange={(e) => setSku(e.target.value || undefined)}
        >
          {(data?.candidate_skus ?? []).map((c) => (
            <option key={c.sku} value={c.sku}>{c.name}</option>
          ))}
        </select>
        {/* Latency pill moved to the TopBar — see LatencyBadge. */}
      </div>

      {error && (
        <ErrorState
          title="Couldn't load Product Filling"
          message={`Aito returned an error. ${error}`}
          command="./do load-data"
        />
      )}

      {!error && (
        <div className="two-col">
          {/* Input card */}
          <div className="card">
            <div className="card-sub" style={{ marginBottom: 6 }}>
              Input · what the catalog has
            </div>
            <div className="page-title" style={{ fontSize: 17, margin: "4px 0 12px" }}>
              {data?.product.name ?? "Loading…"}
            </div>
            <div className="card-sub" style={{ marginBottom: 12 }}>
              {data?.product.brand}
              {data?.product.price_eur != null && <> · {fmtEur(data.product.price_eur)}</>}
            </div>

            {data?.fields.map((f) => (
              <div className="fill-field" key={`input-${f.field}`}>
                <div className="fill-field-label">{f.label}</div>
                <div className="fill-field-val">
                  <InputValue product={data.product} field={f} />
                </div>
              </div>
            ))}
            {!data && (
              <div style={{ height: 240, background: "var(--border-light)", borderRadius: 4 }} />
            )}
          </div>

          {/* Aito-filled card */}
          <div className="card" style={{ borderTop: "3px solid var(--cta)" }}>
            <div className="card-sub" style={{ marginBottom: 6 }}>
              Aito filled · five `_predict` calls in parallel
            </div>
            <div className="page-title" style={{ fontSize: 17, margin: "4px 0 12px" }}>
              {data?.product.name ?? "Loading…"}
            </div>
            <div className="card-sub" style={{ marginBottom: 12 }}>
              from <code>name</code> + <code>brand</code> tokens
            </div>

            {(loading || !data) && (
              <div style={{ height: 240, background: "var(--border-light)", borderRadius: 4 }} />
            )}
            {!loading && data?.fields.map((f) => (
              <div className="fill-field" key={`out-${f.field}`}>
                <div className="fill-field-label">{f.label}</div>
                <div className="fill-field-val" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontWeight: 600 }}>{formatValue(f.predicted_value)}</span>
                  <ConfChip p={f.confidence} />
                  {f.why_factors.length > 0 && (
                    <WhyTooltip
                      factors={f.why_factors.map((w) => ({
                        field: w.field || "name",
                        value: w.value,
                        lift: w.lift,
                      }))}
                    />
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}


// ── Small UI helpers ──────────────────────────────────────────────


function InputValue({
  product,
  field,
}: {
  product: FillingResponse["product"];
  field: FillingFieldOut;
}) {
  // For the two "stored" fields (pet_type, category), show the
  // stored value with a 🔒 chip so the user can see the Aito
  // prediction lines up with what the DB already had.
  if (field.hidden_for_demo) {
    const stored = product[field.field as keyof typeof product];
    return (
      <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
        <span style={{ color: "var(--text-muted)" }}>{String(stored)}</span>
        <span
          className="pill pill-grey"
          title="Stored in the DB — Aito's prediction is shown for reference"
          style={{ fontSize: 10 }}
        >
          🔒 stored
        </span>
      </span>
    );
  }
  // Actually-null field
  const stored = product[field.field as keyof typeof product];
  if (stored == null) {
    return (
      <span style={{ color: "var(--text-muted)", fontStyle: "italic" }}>
        — null —
      </span>
    );
  }
  return <span>{String(stored)}</span>;
}


function ConfChip({ p }: { p: number }) {
  const tier = confClass(p);
  const colorVar =
    tier === "conf-high" ? "var(--green)" :
    tier === "conf-mid"  ? "var(--cta)"   :
    "var(--red)";
  const bgVar =
    tier === "conf-high" ? "var(--green-bg)" :
    tier === "conf-mid"  ? "var(--cta-bg)"   :
    "var(--red-bg)";
  return (
    <span
      className="fill-conf"
      style={{ background: bgVar, color: colorVar }}
    >
      {Math.round(p * 100)}%
    </span>
  );
}


function formatValue(v: string | number | null): string {
  if (v == null) return "—";
  if (typeof v === "number") {
    return Number.isInteger(v) ? String(v) : v.toFixed(1);
  }
  return v;
}


// ── Panel query body pretty-printer (shared shape, kept local) ────


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
