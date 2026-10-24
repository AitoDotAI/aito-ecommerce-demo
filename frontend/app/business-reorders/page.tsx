"use client";

import { Suspense, useEffect, useState } from "react";

import { ApiError, apiFetch } from "@/lib/api";
import { highlightQuery } from "@/lib/highlight-query";
import { businessReordersPanel } from "@/lib/panel-content";
import { usePagePanel, useShell } from "@/components/shell/ShellState";
import ErrorState from "@/components/shell/ErrorState";
import NotFoundNotice from "@/components/shell/NotFoundNotice";
import BoughtTogetherCard from "@/components/business-reorders/BoughtTogetherCard";
import ClaimBox from "@/components/business-reorders/ClaimBox";
import DraftTable from "@/components/business-reorders/DraftTable";
import { fmtDate } from "@/components/business-reorders/format";
import { useUrlState } from "@/lib/use-url-state";
import type { UciBoughtTogether, UciBuyer, UciDraftOrder } from "@/lib/types";


/** A request's state: its data, "not in the data" (404), or another error. */
type Loaded<T> = { data: T | null; notFound: string | null; error: string | null };
const LOADING = { data: null, notFound: null, error: null };

function useApi<T>(path: string | null): Loaded<T> {
  const [state, setState] = useState<Loaded<T>>(LOADING);
  useEffect(() => {
    if (!path) return;
    let current = true;
    setState(LOADING);
    apiFetch<T>(path).then(
      (data) => { if (current) setState({ data, notFound: null, error: null }); },
      (e) => {
        if (!current) return;
        if (e instanceof ApiError && e.status === 404) setState({ data: null, notFound: e.serverMessage ?? e.message, error: null });
        else setState({ data: null, notFound: null, error: String(e) });
      });
    return () => { current = false; };
  }, [path]);
  return state;
}


/**
 * Business reorders (ADR 0034): a wholesaler's buyer, Aito's draft of their
 * next order, and what they really ordered next, on UCI Online Retail II.
 * Data layer: `src/uci_reorder_service.py`, `src/uci_bought_together.py`.
 * The buyer and the product live in the URL (`?customer=12357&code=85123A`).
 */
function BusinessReordersView() {
  usePagePanel(businessReordersPanel(), {
    title: "Business reorders",
    description: "A wholesaler's buyer, Aito's draft of their next order, and what they ordered next.",
    breadcrumb: "Business reorders",
  });
  const { setPanel } = useShell();

  const buyers = useApi<{ buyers: UciBuyer[] }>("/api/uci/buyers");
  const [customerParam, setCustomer] = useUrlState("customer", "");
  const customer = customerParam || buyers.data?.buyers[0]?.customer_id || "";
  const draft = useApi<UciDraftOrder>(customer ? `/api/uci/draft?customer=${encodeURIComponent(customer)}` : null);

  const [codeParam, setCode] = useUrlState("code", "");
  const code = codeParam || draft.data?.lines[0]?.code || "";
  const together = useApi<UciBoughtTogether>(code ? `/api/uci/bought-together?code=${encodeURIComponent(code)}` : null);

  useEffect(() => {
    if (draft.data) setPanel({ ...businessReordersPanel(), query: highlightQuery(draft.data.query) });
  }, [draft.data, setPanel]);

  const options = draft.data?.lines.map((l) => ({ code: l.code, description: l.description })) ?? [];
  if (code && !options.some((o) => o.code === code)) {
    options.unshift({ code, description: together.data?.product.description ?? code });
  }
  const error = buyers.error ?? draft.error ?? together.error;

  return (
    <div className="fade-in">
      <div className="page-header">
        <div className="page-title">Business reorders</div>
        <div className="page-desc">
          Real data: two years of invoices from a UK online giftware wholesaler, many of whose customers are
          businesses. Pick a buyer: Aito drafts their next order from what was ordered before 1 Sep 2011, and
          the ✓ marks what they really ordered next.
        </div>
      </div>

      {error && <ErrorState title="Couldn't load Business reorders" message={`Aito returned an error. ${error}`} command="AITO_ENV=uci ./do uci-load" />}

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
        {buyers.data?.buyers.map((b) => (
          <button key={b.customer_id} className={`customer-chip${b.customer_id === customer ? " selected" : ""}`}
                  onClick={() => setCustomer(b.customer_id)}
                  title={`Ordered next on ${fmtDate(b.next_order_date)}`}>
            {b.customer_id} · {b.prior_invoices} earlier {b.prior_invoices === 1 ? "order" : "orders"}
          </button>
        ))}
      </div>

      {draft.notFound && <NotFoundNotice message={draft.notFound} resetLabel="Show the first buyer" onReset={() => setCustomer("")} />}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 380px), 1fr))", gap: 16 }}>
        <div style={{ display: "grid", gap: 16, alignContent: "start" }}>
          {draft.data ? <DraftTable draft={draft.data} /> : !draft.notFound && <div className="card card-sub">Loading the draft…</div>}
          <ClaimBox />
        </div>
        <div>
          {together.notFound
            ? <NotFoundNotice message={together.notFound} resetLabel="Show the draft's first product" onReset={() => setCode("")} />
            : code && <BoughtTogetherCard options={options} code={code} onPick={setCode} data={together.data} />}
        </div>
      </div>
    </div>
  );
}


// The view reads its state from the URL (`useUrlState`), which the static
// export only allows under a Suspense boundary.
export default function BusinessReordersPage() {
  return (
    <Suspense>
      <BusinessReordersView />
    </Suspense>
  );
}
