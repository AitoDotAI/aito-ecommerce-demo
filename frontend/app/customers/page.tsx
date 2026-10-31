"use client";

import { Suspense, useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";
import type { ProfilesSummary } from "@/lib/customer-profiles";
import { customersPanel } from "@/lib/panel-content";
import { usePagePanel } from "@/components/shell/ShellState";
import ErrorState from "@/components/shell/ErrorState";
import CustomerLookup from "@/components/customers/CustomerLookup";
import PreferencesCard from "@/components/customers/PreferencesCard";
import RelationsCard from "@/components/customers/RelationsCard";
import ResponseMatrix from "@/components/customers/ResponseMatrix";
import SegmentTables from "@/components/customers/SegmentTables";

/**
 * Customers (ADR 0053): how the shop's customers shop, and who responds to what. Traits are counted from
 * purchase history for customers who consented to behavioural profiling; they describe how a customer
 * chooses and which pets they buy for, nothing about the person. Stored and simulated.
 */
function CustomersView() {
  usePagePanel(customersPanel(), {
    title: "Customers",
    description: "How customers shop, and which actions each group responds to.",
    breadcrumb: "Run the shop › Customers",
  });
  const [summary, setSummary] = useState<ProfilesSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<ProfilesSummary>("/api/customer-profiles").then(setSummary).catch((e) => setError(String(e)));
  }, []);

  return (
    <div className="fade-in">
      <div className="page-header">
        <div className="page-title">Customers</div>
        <div className="page-desc">
          How customers shop, counted from what they bought, and which actions each group responds to.
          {summary && <> {summary.profiled.toLocaleString("fi-FI")} of {summary.customers.toLocaleString("fi-FI")} customers
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
        <div style={{ display: "grid", gap: 12 }}>
          <SegmentTables summary={summary} />
          <RelationsCard summary={summary} />
          <PreferencesCard summary={summary} />
          <ResponseMatrix summary={summary} />
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

export default function CustomersPage() {
  return <Suspense fallback={null}><CustomersView /></Suspense>;
}
