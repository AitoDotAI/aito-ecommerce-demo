"use client";

import { Suspense, useCallback, useEffect, useState } from "react";

import { ApiError, apiFetch } from "@/lib/api";
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
import ProductEditor from "@/components/product/ProductEditor";
import { SANDBOX_MONTH, SANDBOX_PARAM } from "@/lib/sandbox";
import { useSetUrlParams, useUrlState } from "@/lib/use-url-state";
import type { LeverStates, ProductCandidate, ProductView as ProductViewData } from "@/lib/types";

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
  // Sandbox mode (ADR 0043): the levers write May 2026, and after each one
  // the page asks its estimates again (`pulled`) from the state read back.
  const [sandbox] = useUrlState(SANDBOX_PARAM, "");
  const [states, setStates] = useState<LeverStates | null>(null);
  const [pulled, setPulled] = useState(0);
  const [noMayYet, setNoMayYet] = useState(false);
  // Outside a sandbox the offer is a preview: the band the owner picked, shown against today's.
  const [previewBand, setPreviewBand] = useState<string | null>(null);
  useEffect(() => { setPreviewBand(null); }, [sku, month]);

  useEffect(() => {
    // Only the request for the product and month now in the URL may update the page.
    let current = true;
    setError(null);
    setNotFound(null);
    setView(null);
    const load = async () => {
      // In a sandbox, May exists for a product only once a lever wrote it.
      const leverStates = sandbox && sku
        ? await apiFetch<LeverStates>(`/api/levers/state?sku=${encodeURIComponent(sku)}`) : null;
      const noMay = month === SANDBOX_MONTH && !leverStates?.next;
      const query = new URLSearchParams();
      if (sku) query.set("sku", sku);
      const asked = noMay ? LATEST_MONTH : month;
      if (asked !== LATEST_MONTH) query.set("month", asked);
      const res = await apiFetch<ProductViewData>(`/api/product${query.size ? `?${query}` : ""}`);
      return { res, leverStates, noMay };
    };
    load().then(({ res, leverStates, noMay }) => {
      if (!current) return;
      setStates(leverStates);
      setNoMayYet(noMay);
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
  }, [sku, month, sandbox, pulled, setPanel]);

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
          <div className="workbench">
            <ProductEditor view={shown} sandbox={sandbox || null} states={states} previewBand={previewBand}
                           onPreview={setPreviewBand}
                           onPulled={() => { if (month === SANDBOX_MONTH) setPulled((n) => n + 1); else setMonth(SANDBOX_MONTH); }} />
            <OfferDecision view={shown} previewBand={sandbox && states ? null : previewBand} />
          </div>
          <div role="tablist" aria-label="Product sections" style={{ display: "flex", gap: 6, marginBottom: 14 }}>
            {TABS.map((t) => (
              <button key={t.id} id={`tab-${t.id}`} role="tab" aria-selected={tab === t.id}
                      className={`toggle-btn${tab === t.id ? " active" : ""}`} onClick={() => setTab(t.id)}
                      style={{ width: "auto", height: "auto", padding: "6px 14px", whiteSpace: "nowrap", fontSize: 13 }}>
                {t.label}
              </button>
            ))}
          </div>
          {noMayYet && (
            <div className="card-sub" style={{ marginBottom: 8 }}>
              May 2026 has no state for this product yet, so the page shows April: pull a lever to write May.
            </div>
          )}
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

// The view reads its state from the URL (`useUrlState`), which the static
// export only allows under a Suspense boundary.
export default function ProductPage() {
  return (
    <Suspense>
      <ProductView />
    </Suspense>
  );
}
