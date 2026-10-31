"use client";

import { Suspense, useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";
import { parseConditions, toggle, type KpiId, type ProfilesSummary, type SegmentView } from "@/lib/customer-profiles";
import { customersPanel } from "@/lib/panel-content";
import { useUrlState } from "@/lib/use-url-state";
import { usePagePanel } from "@/components/shell/ShellState";
import ErrorState from "@/components/shell/ErrorState";
import SegmentAcquisition from "@/components/customers/SegmentAcquisition";
import SegmentFeedback from "@/components/customers/SegmentFeedback";
import SegmentKpis from "@/components/customers/SegmentKpis";
import SegmentHeader from "@/components/customers/SegmentHeader";
import SegmentHighlights from "@/components/customers/SegmentHighlights";
import SegmentOthers from "@/components/customers/SegmentOthers";
import SegmentRelated from "@/components/customers/SegmentRelated";
import SegmentResponse from "@/components/customers/SegmentResponse";
import SegmentTree from "@/components/customers/SegmentTree";
import SegmentTrend from "@/components/customers/SegmentTrend";

const TABS = [
  { id: "highlights", label: "Highlights" }, { id: "figures", label: "Figures" }, { id: "preferences", label: "Preferences" }, { id: "others", label: "Other segments" },
  { id: "channels", label: "Channels" }, { id: "actions", label: "Actions" }, { id: "feedback", label: "Feedback" },
];

/**
 * Customers (ADR 0053): a topic tree selects the segment, by any number of conditions at once ("premium-leaning" and "dog" and
 * "high-margin"), and the page describes the customers who meet all of them. Above the tree, the figure to compare by: each
 * condition shows it as a number and a bar. The segment's name sits on top, then the figure's trend over the months (is the
 * segment in decline?), and below, tabs: highlights (what to do, who they are), key figures and the showing funnel, preferences, other segments, channels, the shop's actions
 * and what the segment says. Nothing ticked is every profiled customer. Traits are counted from purchase history for customers who
 * consented to behavioural profiling; they describe how a customer chooses and which pets they buy for, nothing about the person.
 */
function CustomersView() {
  usePagePanel(customersPanel(), {
    title: "Customers",
    description: "Customer segments by how they shop, with profit per customer, and what each one responds to.",
    breadcrumb: "Run the shop › Customers",
  });
  const [summary, setSummary] = useState<ProfilesSummary | null>(null);
  const [view, setView] = useState<SegmentView | null>(null);
  const [seg, setSeg] = useUrlState("seg", "");
  const [tab, setTab] = useUrlState("tab", "highlights");
  const [kpi, setKpi] = useUrlState("kpi", "revenue_eur");
  const [error, setError] = useState<string | null>(null);
  const conditions = parseConditions(seg);

  useEffect(() => {
    apiFetch<ProfilesSummary>("/api/customer-profiles").then(setSummary).catch((e) => setError(String(e)));
  }, []);

  // The previous segment stays on screen until the next one arrives, so ticking a condition does not blank the page.
  useEffect(() => {
    const query = parseConditions(seg).map((c) => `c=${encodeURIComponent(c)}`).join("&");
    apiFetch<SegmentView>(`/api/customer-profiles/segment${query ? `?${query}` : ""}`).then(setView).catch((e) => setError(String(e)));
  }, [seg]);

  const select = (next: string[]) => setSeg(next.join(","));
  return (
    <div className="fade-in">
      <div className="page-header">
        <div className="page-title">Customers</div>
        <div className="page-desc">
          Customer segments by how they shop, ranked by what a customer earns the shop.
          {summary && <> {summary.profiled.toLocaleString("en-GB")} of {summary.customers.toLocaleString("en-GB")} customers
            are profiled: the others did not consent to behavioural profiling. Simulated data.</>}
        </div>
      </div>
      {error && <ErrorState title="Couldn't load Customers" message={error} command="./do customer-profiles" />}
      {!summary && !error && <div className="card" style={{ height: 160, background: "var(--border-light)" }} />}
      {summary?.scope === "release-not-sandbox" && (
        <div className="card" style={{ borderLeft: "4px solid var(--cta)", marginBottom: 12 }}>
          These profiles are the release&apos;s stored data, not this sandbox&apos;s.
        </div>
      )}
      {summary?.stale && (
        <div className="card" style={{ borderLeft: "4px solid var(--cta)", marginBottom: 12 }}>
          These profiles were stored for data release {summary.release}; the app now serves another.
        </div>
      )}
      {summary && (
        <div className="workbench">
          <SegmentTree summary={summary} view={view} conditions={conditions} kpi={kpi as KpiId} onKpi={setKpi}
                       onToggle={(c) => select(toggle(conditions, c))} onClear={() => select([])} />
          {view && view.too_small && (
            <div className="card" style={{ borderLeft: "4px solid var(--cta)" }}>
              Only {view.customers} customers meet all {conditions.length} conditions. A segment needs {view.min_customers} before the page
              says anything about it: a rate over a handful of customers is not a finding. Untick a condition, or pick one the tree shows more customers for.
            </div>
          )}
          {view && !view.too_small && (
            <div style={{ display: "grid", gap: 12, minWidth: 0 }}>
              <SegmentHeader summary={summary} view={view} />
              <SegmentTrend view={view} kpi={kpi as KpiId} />
              <div role="tablist" aria-label="Segment details" style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                {TABS.map((t) => (
                  <button key={t.id} role="tab" aria-selected={tab === t.id} className={`toggle-btn${tab === t.id ? " active" : ""}`}
                          onClick={() => setTab(t.id)}
                          style={{ width: "auto", height: "auto", padding: "6px 14px", whiteSpace: "nowrap", fontSize: 13 }}>{t.label}</button>
                ))}
              </div>
              {tab === "preferences" ? <SegmentRelated view={view} /> :
               tab === "others" ? <SegmentOthers view={view} kpi={kpi as KpiId} onTick={(c) => select(toggle(conditions, c))} /> :
               tab === "channels" ? <SegmentAcquisition view={view} /> :
               tab === "actions" ? <SegmentResponse summary={summary} view={view} /> :
               tab === "feedback" ? <SegmentFeedback view={view} /> :
               tab === "figures" ? <SegmentKpis summary={summary} view={view} /> :
               <SegmentHighlights summary={summary} view={view} />}
              <div className="card-sub">
                Profit: price paid less unit cost on the lines kept (returned lines earn nothing), less the shop&apos;s action costs; no delivery
                or payment cost is in the data. Unit cost is the inventory&apos;s current cost per product (about two-thirds of the base price)
                applied to two years of sales, and 165 kept lines were sold below it. ± is half the 95 % bootstrap interval of profit per
                customer: a few customers earn much of it. Margin: a customer is high-margin when the gross margin of what they bought is at
                or above the median customer&apos;s ({Math.round(summary.margin_cut * 100)} %). Pets and diets overlap.
              </div>
              <div className="card-sub">
                Every trait is a share of the lines a customer bought: no health, religion or similar is inferred, and the diet
                traits are the pet&apos;s, from the product&apos;s diet tag. They choose which offer or message a customer sees,
                never what price they pay. A customer who withdraws consent is no longer profiled.
              </div>
            </div>
          )}
          {!view && !error && <div className="card" style={{ height: 240, background: "var(--border-light)" }} />}
        </div>
      )}
    </div>
  );
}

export default function CustomersPage() {
  return <Suspense fallback={null}><CustomersView /></Suspense>;
}
