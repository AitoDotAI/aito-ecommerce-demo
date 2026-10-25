"use client";

import { useEffect } from "react";

import { highlightQuery } from "@/lib/highlight-query";
import { acquisitionPanel } from "@/lib/panel-content";
import { usePagePanel, useShell } from "@/components/shell/ShellState";
import ErrorState from "@/components/shell/ErrorState";
import { Card, LiftList, Threshold, fmt, pct, useSection } from "@/components/shop-analytics/LiftParts";
import type { AcquisitionRate, AcquisitionSection, AcquisitionSource } from "@/lib/types";


/**
 * Acquisition (ADR 0040): where customers come from, how each source converts,
 * and whether its customers stay. Data layer: `src/acquisition_service.py`.
 * Sessions are only those of visitors who accepted behavioural tracking
 * (ADR 0044); the stay rate counts every customer.
 */
const LABELS: Record<string, string> = {
  organic_search: "Organic search", paid_search: "Paid search", direct: "Direct",
  email: "Email", affiliate: "Affiliate", social: "Social",
};

export default function AcquisitionPage() {
  usePagePanel(acquisitionPanel(), {
    title: "Acquisition",
    description: "Where customers come from, how each source converts and whether its customers stay.",
    breadcrumb: "Acquisition",
  });
  const { setPanel } = useShell();
  const { data, error } = useSection<AcquisitionSection>("/api/acquisition");

  useEffect(() => {
    if (data) setPanel({ ...acquisitionPanel(data.queries_sent), query: highlightQuery(data.example_query) });
  }, [data, setPanel]);

  return (
    <div className="fade-in">
      <div className="page-header">
        <div className="page-title">Acquisition</div>
        <div className="page-desc">
          A source that converts is not always a source that keeps its customers. Each source below shows both: the
          share of a new visitor&apos;s sessions that end in a first order, and the share of its customers who made
          three or more orders in their first six months.
        </div>
      </div>

      {error && <ErrorState title="Couldn't load Acquisition" message={`Aito returned an error. ${error}`} command="./do load-data" />}

      {data && (
        <>
          <div className="card" style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 14, fontWeight: 600, lineHeight: 1.45, marginBottom: 12 }}>{lead(data.sources)}</div>
            <div style={{ overflowX: "auto" }}>
              <table className="data-table" style={{ width: "100%", minWidth: 640 }}>
                <thead>
                  <tr>
                    <th>Source</th><th>Converts</th><th>Becomes regular</th><th>Predicted to stay</th><th>Visitors land on</th>
                  </tr>
                </thead>
                <tbody>{data.sources.map((s) => <SourceRowView key={s.source} row={s} />)}</tbody>
              </table>
            </div>
            <div className="card-sub" style={{ marginTop: 10 }}>
              Converts: sessions of visitors who accepted tracking, first orders over a new visitor&apos;s sessions.
              Becomes regular: customers who joined at least six months before the data ends. Predicted: Aito&apos;s{" "}
              <code>_predict became_regular</code> from the source alone, with its lift. Intervals are 95 %.
            </div>
          </div>

          <Card title="What the first basket says" sub="First-basket categories over- or under-represented among customers who became regular">
            <LiftList rows={data.regular_basket} unit="regulars" />
            {data.regular_basket.length === 0 && <div className="card-sub">No first-basket category clears the bar.</div>}
            <Threshold significance={{ tested: data.regular_basket.length, z: 1.96, family_confidence: 0.95 }}
                       designEffect="one row per customer, so no clustering" />
          </Card>
        </>
      )}
    </div>
  );
}


function SourceRowView({ row }: { row: AcquisitionSource }) {
  return (
    <tr>
      <td style={{ fontWeight: 600 }}>{LABELS[row.source] ?? row.source}</td>
      <td><Bar rate={row.conversion} scale={0.08} note={`${fmt(row.conversion.successes)} of ${fmt(row.sessions)} sessions`} /></td>
      <td><Bar rate={row.regular} scale={1} note={`${fmt(row.regular.successes)} of ${fmt(row.labelled_customers)} customers`} /></td>
      <td>
        {pct(row.predicted_regular)}
        <div className="card-sub">source ×{row.source_lift.toFixed(2)}</div>
      </td>
      <td>
        {row.landing.length === 0
          ? <span className="card-sub">no category stands out</span>
          : row.landing.map((l) => <div key={l.category}>{l.category.replace("-", " ")} ×{l.lift.toFixed(1)}</div>)}
      </td>
    </tr>
  );
}

/** A share as a bar, with its interval as a whisker; `scale` is the share at full width. */
function Bar({ rate, scale, note }: { rate: AcquisitionRate; scale: number; note: string }) {
  const at = (share: number) => `${Math.min(100, (share / scale) * 100)}%`;
  return (
    <div style={{ minWidth: 140 }}>
      <div style={{ position: "relative", height: 10, background: "var(--bg-subtle, rgba(127,127,127,.15))", borderRadius: 5 }}>
        <div style={{ width: at(rate.successes / rate.total), height: "100%", background: "var(--aito-teal, #14b8a6)", borderRadius: 5 }} />
        <div style={{ position: "absolute", top: 4, height: 2, left: at(rate.low), width: `calc(${at(rate.high)} - ${at(rate.low)})`,
                      background: "var(--text, #222)" }} />
      </div>
      <div style={{ fontSize: 13, marginTop: 3 }}>
        <strong>{pct(rate.successes / rate.total)}</strong>{" "}
        <span className="card-sub">{(rate.low * 100).toFixed(1)}–{(rate.high * 100).toFixed(1)} %</span>
        <div className="card-sub">{note}</div>
      </div>
    </div>
  );
}

/** The sharpest finding: a source that converts at least as well as the middle but whose customers leave. */
function lead(sources: AcquisitionSource[]): string {
  const byConversion = [...sources].sort((a, b) => b.conversion.successes / b.conversion.total - a.conversion.successes / a.conversion.total);
  const middle = byConversion[Math.floor(byConversion.length / 2)];
  const bestStay = Math.max(...sources.map((s) => s.regular.successes / s.regular.total));
  const leaky = byConversion.find((s) =>
    s.conversion.successes / s.conversion.total >= middle.conversion.successes / middle.conversion.total &&
    s.regular.high < bestStay / 2);
  const top = byConversion[0];
  const parts = [`${LABELS[top.source]} converts best, at ${pct(top.conversion.successes / top.conversion.total)} of a new visitor's sessions.`];
  if (leaky) {
    parts.push(`${LABELS[leaky.source]} converts at ${pct(leaky.conversion.successes / leaky.conversion.total)}, but only ` +
      `${pct(leaky.regular.successes / leaky.regular.total)} of its customers become regular: spend on what keeps them.`);
  }
  return parts.join(" ");
}
