"use client";

import { useEffect, useState } from "react";

import { apiFetch, fmtEur } from "@/lib/api";
import { highlightQuery } from "@/lib/highlight-query";
import { retentionPanel } from "@/lib/panel-content";
import { usePagePanel, useShell } from "@/components/shell/ShellState";
import ErrorState from "@/components/shell/ErrorState";
import DecisionCard, { monthName } from "@/components/owner/DecisionCard";
import AtRiskTable from "@/components/retention/AtRiskTable";
import ChurnTells from "@/components/retention/ChurnTells";
import ChurnDrivers from "@/components/retention/ChurnDrivers";
import type { RetentionResponse } from "@/lib/types";

/**
 * Retention (ADR 0041): who is about to leave, why, and what offer brings
 * them back? Merged from Churn and Win-back: the win-back offer is an
 * at-risk row's action. It leads with who to reach and the spend at
 * stake; the score's accuracy is in Evidence › Model checks.
 */
export default function RetentionPage() {
  usePagePanel(retentionPanel(), {
    title: "Retention",
    description: "Who is about to leave, why, and which action brings them back.",
    breadcrumb: "Run the shop › Retention",
  });
  const { setPanel } = useShell();
  const [data, setData] = useState<RetentionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<RetentionResponse>("/api/retention")
      .then((res) => {
        setData(res);
        setPanel({ ...retentionPanel(), query: highlightQuery(res.last_query.body) });
      })
      .catch((e) => setError(String(e)));
  }, [setPanel]);

  return (
    <div className="fade-in">
      <div className="page-header">
        <div className="page-title">Retention</div>
        <div className="page-desc">Who is about to leave, why, and which action brings them back.</div>
      </div>

      {error && <ErrorState title="Couldn't load Retention" message={`Aito returned an error. ${error}`} command="./do load-data" />}
      {!data && !error && <div className="card" style={{ height: 160, background: "var(--border-light)" }} />}

      {data && (
        <>
          <DecisionCard
            decision={`Reach these ${data.decision.customers} customers first`}
            impact={<>
              They spent <strong>{fmtEur(data.decision.spend_12m_eur)}</strong> with the shop in the last 12 months,
              and Aito rates each more likely than not to stop ordering: {data.counts.likely_to_leave} of the{" "}
              {data.counts.active.toLocaleString()} active customers are, and these hold the most spend.{" "}
              The best action differs by customer ({Object.entries(data.decision.best_actions)
                .sort((a, b) => b[1] - a[1]).map(([label, n]) => `${n} × ${label.toLowerCase()}`).join(", ")}) and adds an
              estimated <strong>{fmtEur(data.decision.best_actions_net_eur)}</strong> over doing nothing, after what each
              costs.
            </>}
            note={<>
              As of {monthName(data.as_of_month)}. The risk is Aito&apos;s estimate that a customer&apos;s latest
              order is their last for three months, learned from orders whose next three months are in the
              data (up to {monthName(data.learned_until)}).
            </>}
            evidenceHref="/evidence/model-checks/"
          />

          <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: 16, marginTop: 16 }}>
            <div className="card">
              <div className="card-title">At risk · most spend at stake first</div>
              <AtRiskTable rows={data.at_risk} />
            </div>
            <div className="card">
              <div className="card-title">Tells · what customers who left had been through</div>
              <ChurnTells tells={data.tells} />
              <div className="card-sub" style={{ marginTop: 10 }}>
                Observed, not predicted: NPS, reviews, returns and late deliveries of customers who have gone, against
                customers who ordered as often. A tell that shows no effect is shown as that.
              </div>
            </div>
            <div className="card">
              <div className="card-title">Why · the profiles that churn more</div>
              <ChurnDrivers drivers={data.drivers} withoutEffect={data.driver_fields_without_effect} />
              <div className="card-sub" style={{ marginTop: 10 }}>
                {data.counts.churned.toLocaleString()} customers have already gone (no order in 90 days).
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
