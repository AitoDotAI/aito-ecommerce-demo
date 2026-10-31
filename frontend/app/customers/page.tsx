"use client";

import { Suspense, useEffect, useState } from "react";

import { apiFetch, fmtEur } from "@/lib/api";
import { findSegment, type ProfilesSummary } from "@/lib/customer-profiles";
import { customersPanel } from "@/lib/panel-content";
import { useUrlState } from "@/lib/use-url-state";
import { usePagePanel } from "@/components/shell/ShellState";
import ErrorState from "@/components/shell/ErrorState";
import CustomerLookup from "@/components/customers/CustomerLookup";
import PreferenceGraph from "@/components/customers/PreferenceGraph";
import SegmentAcquisition from "@/components/customers/SegmentAcquisition";
import SegmentBuys from "@/components/customers/SegmentBuys";
import SegmentKpis from "@/components/customers/SegmentKpis";
import SegmentList from "@/components/customers/SegmentList";
import SegmentPicker from "@/components/customers/SegmentPicker";
import SegmentProfile from "@/components/customers/SegmentProfile";
import SegmentRelations from "@/components/customers/SegmentRelations";
import SegmentResponse from "@/components/customers/SegmentResponse";

/**
 * Customers (ADR 0053): pick a segment and every pane follows it, as in Product. The profile and what to do sit
 * top left, the key figures and the showing funnel top right; below, how customers rank by a preference and where the
 * segment sits in that ranking, how it relates to other variables, what it buys, and what the shop's actions did for it.
 * Traits are counted from purchase history for customers who consented to behavioural profiling; they describe how a
 * customer chooses and which pets they buy for, nothing about the person. Stored and simulated.
 */
function CustomersView() {
  usePagePanel(customersPanel(), {
    title: "Customers",
    description: "Customer segments by how they shop, with profit per customer, and what each one responds to.",
    breadcrumb: "Run the shop › Customers",
  });
  const [summary, setSummary] = useState<ProfilesSummary | null>(null);
  const [selected, setSelected] = useUrlState("seg", "all");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<ProfilesSummary>("/api/customer-profiles").then(setSummary).catch((e) => setError(String(e)));
  }, []);

  const key = summary && findSegment(summary, selected) ? selected : "all";
  return (
    <div className="fade-in">
      <div className="page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 12 }}>
        <div>
          <div className="page-title">Customers</div>
          <div className="page-desc">
            Customer segments by how they shop, ranked by what a customer earns the shop.
            {summary && <> {summary.profiled.toLocaleString("fi-FI")} of {summary.customers.toLocaleString("fi-FI")} customers
              are profiled: the others did not consent to behavioural profiling. Simulated data.</>}
          </div>
        </div>
        {summary && <SegmentPicker summary={summary} selected={key} onSelect={setSelected} />}
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
        <div style={{ display: "grid", gap: 12 }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 380px), 1fr))", gap: 12, alignItems: "start" }}>
            <SegmentProfile summary={summary} selected={key} />
            <SegmentKpis summary={summary} selected={key} />
          </div>
          <PreferenceGraph summary={summary} selected={key} />
          <SegmentAcquisition summary={summary} selected={key} />
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 420px), 1fr))", gap: 12, alignItems: "start" }}>
            <div style={{ display: "grid", gap: 12 }}>
              <SegmentRelations summary={summary} selected={key} />
              <SegmentBuys summary={summary} selected={key} />
            </div>
            <SegmentResponse summary={summary} selected={key} />
          </div>
          <SegmentList summary={summary} selected={key} onSelect={setSelected} />
          <Headline summary={summary} />
          <CustomerLookup />
          <div className="card-sub">
            Every trait is a share of the lines a customer bought: no health, religion or similar is inferred, and the diet
            traits are the pet&apos;s, from the product&apos;s diet tag. They choose which offer or message a customer sees,
            never what price they pay. A customer who withdraws consent is no longer profiled, and cannot be looked up by name.
          </div>
        </div>
      )}
    </div>
  );
}

function Headline({ summary }: { summary: ProfilesSummary }) {
  const d = summary.profit_distribution;
  const items: [string, string, string][] = [
    ["Profit, profiled customers", fmtEur(summary.profiled_profit_eur), `${Math.round(summary.gross_margin * 100)} % gross margin`],
    ["Profit per customer", fmtEur(summary.profiled_profit_eur / summary.profiled), `median ${fmtEur(d.median_eur)}`],
    ["Top tenth earns", `${Math.round(d.top_tenth_share * 100)} %`, "of the profit"],
    ["Lose money", String(d.losing_money), `of ${d.customers.toLocaleString("fi-FI")}`],
  ];
  return (
    <div className="card" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 12 }}>
      {items.map(([label, value, note]) => (
        <div key={label}>
          <div className="card-sub">{label}</div>
          <div style={{ fontSize: 22, fontWeight: 700 }}>{value}</div>
          <div className="card-sub">{note}</div>
        </div>
      ))}
    </div>
  );
}

export default function CustomersPage() {
  return <Suspense fallback={null}><CustomersView /></Suspense>;
}
