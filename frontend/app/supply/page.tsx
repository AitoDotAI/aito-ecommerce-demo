"use client";

import { Suspense, useEffect, useState } from "react";

import { apiFetch, fmtEur } from "@/lib/api";
import { highlightQuery } from "@/lib/highlight-query";
import { supplyPanel } from "@/lib/panel-content";
import { useUrlState } from "@/lib/use-url-state";
import { usePagePanel, useShell } from "@/components/shell/ShellState";
import ErrorState from "@/components/shell/ErrorState";
import DecisionCard, { monthName } from "@/components/owner/DecisionCard";
import ReorderTable from "@/components/supply/ReorderTable";
import OverstockTable from "@/components/supply/OverstockTable";
import { PriceOutliers, TopMovers } from "@/components/supply/MoversAndOutliers";
import type { SupplyResponse } from "@/lib/types";

const MODEL_CHECKS = "/evidence/model-checks/";

/**
 * Supply (ADR 0041): what do I reorder, what is overstocked, and what
 * markdown clears it? Merged from Inventory, Demand, Markdown and Price's
 * fair-band table. It leads with the two decisions and their estimated
 * euros; each row carries its price band. The forecast's accuracy is in
 * Evidence › Model checks. `?sku=` highlights that product's row.
 */
function SupplyView() {
  usePagePanel(supplyPanel(), {
    title: "Supply",
    description: "What to reorder, what is overstocked, and what markdown clears it.",
    breadcrumb: "Run the shop › Supply",
  });
  const { setPanel } = useShell();
  const [sku] = useUrlState("sku", "");
  const [data, setData] = useState<SupplyResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<SupplyResponse>("/api/supply")
      .then((res) => {
        setData(res);
        setPanel({ ...supplyPanel(), query: highlightQuery(res.last_query.body) });
      })
      .catch((e) => setError(String(e)));
  }, [setPanel]);

  useEffect(() => {
    if (data && sku) document.getElementById(`row-${sku}`)?.scrollIntoView({ block: "center" });
  }, [data, sku]);

  const month = data ? monthName(data.forecast_month) : "";
  return (
    <div className="fade-in">
      <div className="page-header">
        <div className="page-title">Supply</div>
        <div className="page-desc">
          What to reorder, what is overstocked, and what markdown clears it.
          {data && <> Forecasts are Aito&apos;s estimates for {month}; euros follow from them.</>}
        </div>
      </div>

      {error && <ErrorState title="Couldn't load Supply" message={`Aito returned an error. ${error}`} command="./do load-data" />}
      {!data && !error && <div className="card" style={{ height: 160, background: "var(--border-light)" }} />}

      {data && (
        <>
          <div className="two-col">
            <DecisionCard
              decision={`Reorder these ${data.reorder.skus} now`}
              impact={<>
                Without them, an estimated <strong>{fmtEur(data.reorder.revenue_at_risk_eur)}</strong> of {month}&apos;s
                sales can&apos;t be served. The orders total {data.reorder.units} units,{" "}
                {fmtEur(data.reorder.order_cost_eur)} at cost.
              </>}
              note={`Each order covers Aito's ${month} forecast plus safety stock.`}
              evidenceHref={MODEL_CHECKS}
            />
            <DecisionCard
              tone="warn"
              decision={`${fmtEur(data.overstock_decision.tied_capital_eur)} tied up in ${data.overstock_decision.skus} overstocked products`}
              impact={<OverstockLine d={data.overstock_decision} />}
              note="Markdowns are tested at 5–20 % off; a quarter (13 weeks) is the time to clear."
              evidenceHref={MODEL_CHECKS}
            />
          </div>

          <div className="card" style={{ marginBottom: 16 }}>
            <div className="card-title">Reorder now · below the reorder point</div>
            <ReorderTable rows={data.reorder_queue} month={month} highlight={sku} />
          </div>

          <div className="card" style={{ marginBottom: 16 }}>
            <div className="card-title">Overstock · the {data.overstock.length} with the most capital tied up</div>
            <OverstockTable rows={data.overstock} highlight={sku} />
          </div>

          <div className="two-col">
            <div className="card">
              <div className="card-title">Top movers · {month} forecast</div>
              <TopMovers rows={data.top_movers} month={month} />
            </div>
            <div className="card">
              <div className="card-title">Priced outside their band · {data.price_outliers.length} products</div>
              <PriceOutliers rows={data.price_outliers} />
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function OverstockLine({ d }: { d: SupplyResponse["overstock_decision"] }) {
  return (
    <>
      Of the {d.scored} largest, <strong>{d.hold}</strong> sell through at full price within a quarter
      {d.markdown > 0 && <>; a markdown clears <strong>{d.markdown}</strong> ({d.markdown_units_cleared} units,
        an estimated {fmtEur(d.markdown_capital_freed_eur)} freed for {fmtEur(d.markdown_margin_given_up_eur)} of margin)</>}
      {d.wont_clear > 0 && <>; <strong>{d.wont_clear}</strong> don&apos;t clear by price alone, even at 20 % off.
        That counts price only: an offer&apos;s lift on purchases when shown, and the higher place it earns in the
        shop, aren&apos;t in this estimate</>}.
    </>
  );
}

// The view reads `?sku=` from the URL, which the static export only allows under Suspense.
export default function SupplyPage() {
  return (
    <Suspense>
      <SupplyView />
    </Suspense>
  );
}
