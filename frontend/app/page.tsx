"use client";

import { useEffect, useState } from "react";

import { apiFetch, fmtEur } from "@/lib/api";
import { highlightQuery } from "@/lib/highlight-query";
import { overviewPanel } from "@/lib/panel-content";
import { usePagePanel, useShell } from "@/components/shell/ShellState";
import ErrorState from "@/components/shell/ErrorState";
import { BestSellers, HeadlineCard, HouseholdCards, KpiCard, MonthlyBars, changeOnBefore } from "@/components/overview/OverviewParts";
import type { OverviewResponse } from "@/lib/types";

const DESCRIPTION = "How the shop is doing, and where to look: one headline per owner view, each a link.";

/**
 * Overview (ADR 0041) — "How is the shop doing, and where should I look?"
 * The last 12 months against the 12 before, one headline per owner view,
 * the best sellers, and the households. Data layer:
 * `src/overview_service.py` (precomputed) and `src/overview_headlines.py`.
 */
export default function OverviewPage() {
  usePagePanel(overviewPanel(), { title: "Overview", description: DESCRIPTION, breadcrumb: "Overview" });

  const { setPanel, demoMode } = useShell();
  // Demo mode hides the year-on-year comparison: the generated shop grows
  // +300 % a year, which reads as fiction in a meeting. The counts stay.
  const growth = (now: number, before: number, monthsBefore: number) =>
    demoMode ? null : changeOnBefore(now, before, monthsBefore);
  const [data, setData] = useState<OverviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<OverviewResponse>("/api/overview").then(setData).catch((e) => setError(String(e)));
  }, []);
  useEffect(() => {
    if (data) setPanel({ ...overviewPanel(), query: highlightQuery(data.last_query.body) });
  }, [data, setPanel]);

  const k = data?.kpis;
  const window12 = k ? `${k.first_month} … ${k.last_month}` : "last 12 months";
  return (
    <div className="fade-in">
      <div className="page-header">
        <div className="page-title">Overview</div>
        <div className="page-desc">{DESCRIPTION}</div>
      </div>

      {error && <ErrorState title="Couldn't load the Overview" message={`Aito returned an error. ${error}`} command="./do load-data" />}

      <div className="kpi-grid">
        <KpiCard label={`Orders · ${window12}`} accent="kpi-accent"
                 value={k ? k.orders.toLocaleString("en-US") : "…"}
                 change={k && growth(k.orders, k.orders_before, k.months_before)} />
        <KpiCard label="Revenue" accent="kpi-accent-green"
                 value={k ? fmtEur(k.revenue_eur) : "…"}
                 change={k && growth(k.revenue_eur, k.revenue_before_eur, k.months_before)} />
        <KpiCard label="Average basket" accent="kpi-accent-blue" value={k ? fmtEur(k.avg_basket_eur, 2) : "…"} />
        <KpiCard label="Customers ordering" accent="kpi-accent-purple"
                 value={k ? k.customers_ordering.toLocaleString("en-US") : "…"}
                 change={k && `of ${k.customers.toLocaleString("en-US")} · ${k.products} products`} />
      </div>

      <div className="card-title" style={{ margin: "4px 0 10px" }}>Where to look</div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(300px, 100%), 1fr))",
                    gap: 12, marginBottom: 20 }}>
        {data?.headlines.map((h) => <HeadlineCard key={h.view} h={h} />)}
        {!data && !error && <div className="card-sub">Loading…</div>}
      </div>

      <div className="two-col">
        <div className="card">
          <div className="card-title">Revenue and orders per month</div>
          <div className="card-sub" style={{ marginBottom: 12 }}>Every month in the data, newest first</div>
          {data && <MonthlyBars months={data.monthly} />}
        </div>
        <div className="card">
          <div className="card-title">Best sellers</div>
          <div className="card-sub" style={{ marginBottom: 12 }}>Units sold, {window12} · open one in Product</div>
          {data && <BestSellers products={data.top_products} />}
        </div>
      </div>

      <div className="card">
        <div className="card-title">Households</div>
        <div className="card-sub" style={{ marginBottom: 12 }}>
          By the pets they declared · what each buys more of is in{" "}
          <a href="/patterns/?who=dog">Patterns › Who buys what</a>
        </div>
        {data && <HouseholdCards households={data.households} />}
      </div>
    </div>
  );
}
