"use client";

import { Suspense, useCallback, useEffect, useState } from "react";

import { ApiError, apiFetch, fmtEur } from "@/lib/api";
import { highlightQuery } from "@/lib/highlight-query";
import { productPanel } from "@/lib/panel-content";
import { usePagePanel, useShell } from "@/components/shell/ShellState";
import ErrorState from "@/components/shell/ErrorState";
import NotFoundNotice from "@/components/shell/NotFoundNotice";
import OfferDecision from "@/components/product/OfferDecision";
import ProductBuyers from "@/components/product/ProductBuyers";
import ProductHistory from "@/components/product/ProductHistory";
import ProductPicker from "@/components/product/ProductPicker";
import ProductWhatIf from "@/components/product/ProductWhatIf";
import { BAND_LABEL, monthLabel, words } from "@/components/product/labels";
import { useSetUrlParams, useUrlState } from "@/lib/use-url-state";
import type { ProductCandidate, ProductView as ProductViewData } from "@/lib/types";

const LATEST_MONTH = "2026-04";
const TABS = [
  { id: "what-if", label: "What if" },
  { id: "history", label: "History" },
  { id: "for-whom", label: "For whom" },
];

/**
 * Product (ADR 0041): the product manager's view of one product in one
 * month. It leads with the discount decision and its estimated effect,
 * then the levers (What if), the record (History) and the buyers (For
 * whom). Product, month, tab and the what-if price live in the URL.
 * Backend: src/product_service.py.
 */
function ProductView() {
  usePagePanel(productPanel(), {
    title: "Product",
    description: "One product: what an offer or a price change would do, its history, and who buys it.",
    breadcrumb: "Product",
  });

  const { setPanel } = useShell();
  const [sku] = useUrlState("sku", "");
  const [month, setMonth] = useUrlState("month", LATEST_MONTH);
  const [tab, setTab] = useUrlState("tab", "what-if");
  const [priceParam] = useUrlState("price", "");
  const setUrl = useSetUrlParams();
  const [view, setView] = useState<ProductViewData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState<string | null>(null);
  // Kept across a failed load, so the picker still works after a bad link.
  const [candidates, setCandidates] = useState<ProductCandidate[]>([]);
  const [months, setMonths] = useState<string[]>([LATEST_MONTH]);

  useEffect(() => {
    // Only the request for the product and month now in the URL may update the page.
    let current = true;
    setError(null);
    setNotFound(null);
    setView(null);
    const query = new URLSearchParams();
    if (sku) query.set("sku", sku);
    if (month !== LATEST_MONTH) query.set("month", month);
    apiFetch<ProductViewData>(`/api/product${query.size ? `?${query}` : ""}`).then((res) => {
      if (!current) return;
      setView(res);
      setCandidates(res.candidates);
      setMonths(res.history.months.map((m) => m.month));
      setPanel({ ...productPanel(), query: highlightQuery(res.last_query.body) });
    }, (e) => {
      if (!current) return;
      if (e instanceof ApiError && e.status === 404) setNotFound(e.serverMessage ?? e.message);
      else setError(String(e));
    });
    return () => { current = false; };
  }, [sku, month, setPanel]);

  const showQuery = useCallback(
    (body: Record<string, unknown>) => setPanel({ ...productPanel(), query: highlightQuery(body) }),
    [setPanel],
  );
  const pickPrice = useCallback((p: number) => setUrl({ price: p.toFixed(2) }), [setUrl]);
  const shown = view && (!sku || view.product.sku === sku) ? view : null;

  return (
    <div className="fade-in">
      <div className="page-header">
        <div className="page-title">Product</div>
        <div className="page-desc">
          What will this product do, why, and what if you change its discount or price? For whom?
        </div>
      </div>

      <ProductPicker products={candidates} sku={sku || shown?.product.sku || ""} months={months} month={month}
                     onSku={(next) => setUrl({ sku: next, price: null })} onMonth={setMonth} />

      {notFound && (
        <NotFoundNotice message={notFound} resetLabel="Show the default product" onReset={() => setUrl({ sku: null, month: null, price: null })} />
      )}
      {error && (
        <ErrorState title="Couldn't load the product" message={`Aito returned an error. ${error}`} command="./do load-data" />
      )}
      {!error && !notFound && !shown && <div className="card" style={{ height: 320, background: "var(--border-light)" }} />}

      {shown && (
        <>
          <ProductHeader view={shown} />
          <OfferDecision view={shown} />
          <div role="tablist" aria-label="Product sections" style={{ display: "flex", gap: 6, marginBottom: 14 }}>
            {TABS.map((t) => (
              <button key={t.id} id={`tab-${t.id}`} role="tab" aria-selected={tab === t.id}
                      className={`toggle-btn${tab === t.id ? " active" : ""}`} onClick={() => setTab(t.id)}
                      style={{ width: "auto", height: "auto", padding: "6px 14px", whiteSpace: "nowrap", fontSize: 13 }}>
                {t.label}
              </button>
            ))}
          </div>
          {tab === "what-if" && (
            <ProductWhatIf view={shown} price={priceParam ? Number(priceParam) : null}
                           onPrice={pickPrice} onQuery={showQuery} />
          )}
          {tab === "history" && <ProductHistory history={shown.history} month={shown.month} />}
          {tab === "for-whom" && <ProductBuyers view={shown} />}
        </>
      )}
    </div>
  );
}

function ProductHeader({ view }: { view: ProductViewData }) {
  const { product: p, state: s } = view;
  const facts = [
    s.discount_band === "none" ? `at list price, ${fmtEur(s.price_eur, 2)}` : `${BAND_LABEL[s.discount_band]}, ${fmtEur(s.price_eur, 2)}`,
    s.rating_band === "unrated" ? "no stars yet" : `${s.rating_band} stars`,
    s.age,
    ...(s.rival_launched ? ["a rival launched recently"] : []),
    ...(s.price_change === "rise" ? ["after a price rise"] : []),
    `sold ${s.units_sold}`,
    `${s.reviews} review${s.reviews === 1 ? "" : "s"}`,
  ];
  return (
    <div style={{ margin: "4px 0 14px" }}>
      <div style={{ fontWeight: 700, fontSize: 18 }}>{p.name}</div>
      <div className="card-sub">
        {p.brand} · {words(p.pet_type)} · {words(p.category)} · list {fmtEur(p.price_eur, 2)} · cost {fmtEur(p.unit_cost_eur, 2)}
      </div>
      <div style={{ fontSize: 13, marginTop: 4 }}>
        <strong>{monthLabel(view.month)}:</strong> {facts.join(" · ")}
      </div>
    </div>
  );
}

// The view reads its state from the URL (`useUrlState`), which the static
// export only allows under a Suspense boundary.
export default function ProductPage() {
  return (
    <Suspense>
      <ProductView />
    </Suspense>
  );
}
