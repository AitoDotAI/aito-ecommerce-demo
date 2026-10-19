"use client";

import { Suspense, useEffect, useState } from "react";

import { ApiError, apiFetch, fmtEur } from "@/lib/api";
import { highlightQuery } from "@/lib/highlight-query";
import { productInsightsPanel } from "@/lib/panel-content";
import { usePagePanel, useShell } from "@/components/shell/ShellState";
import ErrorState from "@/components/shell/ErrorState";
import NotFoundNotice from "@/components/shell/NotFoundNotice";
import { useUrlState } from "@/lib/use-url-state";
import type { ProductInsightsBuyerRow, ProductInsightsResponse } from "@/lib/types";


/**
 * Product Insights — one product's funnel, surfaces, buyers, monthly
 * units and reviews (ADR 0028). Data layer:
 * `src/product_insights_service.py`. The product lives in the URL
 * (`?sku=`), so a link opens the same product.
 */
function ProductInsightsView() {
  usePagePanel(productInsightsPanel(), {
    title: "Product Insights",
    description: "One product: how it converts, where, and who buys it.",
    breadcrumb: "Product Insights",
  });

  const { setPanel } = useShell();
  const [sku, setSku] = useUrlState("sku", "");
  const [data, setData] = useState<ProductInsightsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState<string | null>(null);
  // Kept across a failed load, so the picker still works after a bad link.
  const [candidates, setCandidates] = useState<ProductInsightsResponse["candidate_products"]>([]);

  useEffect(() => {
    // Picking quickly can leave an older request finishing last; only the
    // request for the product now in the URL may update the page.
    let current = true;
    setError(null);
    setNotFound(null);
    setData(null);
    apiFetch<ProductInsightsResponse>(
      sku ? `/api/product-insights?sku=${encodeURIComponent(sku)}` : "/api/product-insights",
    ).then((res) => {
      if (!current) return;
      setData(res);
      setCandidates(res.candidate_products);
      setPanel({ ...productInsightsPanel(), query: highlightQuery(res.last_query.body) });
    }, (e) => {
      if (!current) return;
      if (e instanceof ApiError && e.status === 404) setNotFound(e.serverMessage ?? e.message);
      else setError(String(e));
    });
    return () => { current = false; };
  }, [sku, setPanel]);

  return (
    <div className="fade-in">
      <div className="page-header">
        <div className="page-title">Product Insights</div>
        <div className="page-desc">
          One product: how it converts, on which surface, and which customers buy it more than
          average (<code>_relate</code> over its order lines).
        </div>
      </div>

      <div className="search-wrap" style={{ flexWrap: "wrap" }}>
        <label htmlFor="sku-picker" style={{ fontSize: 12, fontWeight: 600, color: "var(--text-muted)" }}>
          Product
        </label>
        <select
          id="sku-picker"
          className="search-input"
          style={{ paddingLeft: 12, width: "auto", minWidth: 360 }}
          value={sku || data?.product.sku || ""}
          onChange={(e) => setSku(e.target.value)}
        >
          {groupByCategory(candidates).map(([group, products]) => (
            <optgroup key={group} label={group}>
              {products.map((p) => <option key={p.sku} value={p.sku}>{p.name}</option>)}
            </optgroup>
          ))}
        </select>
        {data?.bought_together_anchor && (
          <a href={`/bought-together/?anchor=${data.bought_together_anchor}`} style={{ fontSize: 13 }}>
            What's bought with {data.product.category.replace(/-/g, " ")} →
          </a>
        )}
      </div>

      {notFound && (
        <NotFoundNotice message={notFound} resetLabel="Show the default product" onReset={() => setSku("")} />
      )}

      {error && (
        <ErrorState title="Couldn't load Product Insights" message={`Aito returned an error. ${error}`} command="./do load-data" />
      )}

      {!error && !notFound && !data && <div className="card" style={{ height: 240, background: "var(--border-light)" }} />}

      {!error && data && (
        <>
          <div className="card-sub" style={{ marginBottom: 12 }}>
            {data.product.name} · {data.product.brand} · {fmtEur(data.product.price_eur)}
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 16 }}>
            <FunnelCard funnel={data.funnel} />
            <SurfacesCard surfaces={data.surfaces} />
            <BuyersCard buyers={data.buyers} />
            <MonthlyCard monthly={data.monthly} />
            <ReviewsCard ratings={data.ratings} sentiments={data.sentiments} />
          </div>
        </>
      )}
    </div>
  );
}


const STEP_LABELS: Record<string, string> = {
  impressions: "Shown", clicked: "Clicked", added_to_cart: "Added to cart", purchased: "Purchased",
};

function FunnelCard({ funnel }: { funnel: ProductInsightsResponse["funnel"] }) {
  const top = funnel[0]?.count || 1;
  return (
    <Card title="Funnel" sub="Impressions → purchase, each rate of the step before">
      {funnel.map((s, i) => (
        <Bar key={s.step} label={STEP_LABELS[s.step]} value={s.count} share={s.count / top}
             note={i === 0 ? "" : `${pct(s.count, funnel[i - 1].count)} of ${STEP_LABELS[funnel[i - 1].step].toLowerCase()}`} />
      ))}
    </Card>
  );
}

function SurfacesCard({ surfaces }: { surfaces: ProductInsightsResponse["surfaces"] }) {
  const top = Math.max(1, ...surfaces.map((s) => s.impressions));
  return (
    <Card title="By surface" sub="Where it was shown, and how often that ended in a purchase">
      {surfaces.map((s) => (
        <Bar key={s.surface} label={s.surface.replace(/_/g, " ")} value={s.impressions} share={s.impressions / top}
             note={`${s.purchased} purchased (${pct(s.purchased, s.impressions)})`} />
      ))}
    </Card>
  );
}

function BuyersCard({ buyers }: { buyers: ProductInsightsBuyerRow[] }) {
  return (
    <Card title="Who buys it" sub="Profiles over- or under-represented in its order lines vs all order lines. Order lines include purchases with no tracked impression, so they can outnumber the funnel's purchases.">
      {buyers.slice(0, 8).map((b) => (
        <div key={`${b.field}-${b.value}`} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", fontSize: 13 }}>
          <span>
            <span style={{ color: "var(--text-muted)" }}>{b.field.replace(/^order_id\.customer_id\./, "declared ").replace("declared region", "region").replace(/_/g, " ")}</span>
            {" = "}{b.value.replace(/_/g, " ")}
            <span style={{ color: "var(--text-muted)", fontSize: 11 }}> · {b.lines} of {b.lines_total} lines</span>
          </span>
          <strong style={{ color: liftColor(b) }}>{b.lift.toFixed(2)}×</strong>
        </div>
      ))}
    </Card>
  );
}

function MonthlyCard({ monthly }: { monthly: ProductInsightsResponse["monthly"] }) {
  const top = Math.max(1, ...monthly.map((m) => m.units_sold));
  return (
    <Card title="Units per month" sub="From monthly_sales; a month without a row sold 0 units and shows as 0">
      <div style={{ display: "flex", alignItems: "flex-end", gap: 2, height: 120 }}>
        {monthly.map((m) => (
          <div key={m.month} title={`${m.month}: ${m.units_sold} units`}
               style={{ flex: 1, height: `${(m.units_sold / top) * 100}%`, minHeight: 1, background: "var(--cta)" }} />
        ))}
      </div>
      {monthly.length > 0 && (
        <div className="card-sub" style={{ display: "flex", justifyContent: "space-between", marginTop: 4 }}>
          <span>{monthly[0].month}</span><span>{monthly[monthly.length - 1].month}</span>
        </div>
      )}
    </Card>
  );
}

function ReviewsCard({ ratings, sentiments }: { ratings: Record<string, number>; sentiments: Record<string, number> }) {
  const total = Object.values(ratings).reduce((a, b) => a + b, 0);
  const top = Math.max(1, ...Object.values(ratings));
  return (
    <Card title="Reviews" sub={`${total} reviews · ${Object.entries(sentiments).map(([s, n]) => `${n} ${s}`).join(", ")}`}>
      {["5", "4", "3", "2", "1"].map((r) => (
        <Bar key={r} label={"★".repeat(Number(r))} value={ratings[r]} share={ratings[r] / top} note="" />
      ))}
    </Card>
  );
}


function Card({ title, sub, children }: { title: string; sub: string; children: React.ReactNode }) {
  return (
    <div className="card">
      <div className="page-title" style={{ fontSize: 16, margin: "0 0 4px" }}>{title}</div>
      <div className="card-sub" style={{ marginBottom: 12 }}>{sub}</div>
      {children}
    </div>
  );
}

function Bar({ label, value, share, note }: { label: string; value: number; share: number; note: string }) {
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
        <span>{label}</span>
        <span><strong>{value}</strong>{note && <span style={{ color: "var(--text-muted)", fontSize: 11 }}> · {note}</span>}</span>
      </div>
      <div style={{ height: 6, background: "var(--border-light)", borderRadius: 3 }}>
        <div style={{ width: `${share * 100}%`, height: "100%", background: "var(--cta)", borderRadius: 3 }} />
      </div>
    </div>
  );
}

// Within ±0.15 of 1 is "no difference", the same band the Churn drivers
// use; so is a lift on fewer than 10 lines (the service ranks those last).
function liftColor(b: ProductInsightsBuyerRow): string {
  if (Math.abs(b.lift - 1) < 0.15 || b.lines < 10) return "var(--text-muted)";
  return b.lift > 1 ? "var(--green)" : "var(--red)";
}

function pct(part: number, whole: number): string {
  return whole === 0 ? "–" : `${Math.round((part / whole) * 100)}%`;
}

function groupByCategory(products: ProductInsightsResponse["candidate_products"]) {
  const groups = new Map<string, ProductInsightsResponse["candidate_products"]>();
  for (const p of products) {
    const key = `${p.pet_type.replace(/_/g, " ")} · ${p.category.replace(/-/g, " ")}`;
    groups.set(key, [...(groups.get(key) ?? []), p]);
  }
  return [...groups.entries()];
}


// The view reads its state from the URL (`useUrlState`), which the static
// export only allows under a Suspense boundary.
export default function ProductInsightsPage() {
  return (
    <Suspense>
      <ProductInsightsView />
    </Suspense>
  );
}
