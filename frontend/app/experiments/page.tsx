"use client";

import { Suspense, useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";
import { experimentsPanel } from "@/lib/panel-content";
import { ARMS, type ExperimentsData } from "@/lib/experiments";
import { usePagePanel } from "@/components/shell/ShellState";
import ErrorState from "@/components/shell/ErrorState";
import ExperimentDetail from "@/components/experiments/ExperimentDetail";
import ExperimentList from "@/components/experiments/ExperimentList";
import PersonalChoice from "@/components/experiments/PersonalChoice";
import { useUrlState } from "@/lib/use-url-state";

/**
 * Experiments (ADR 0064): A/B tests on how a product is shown (its offer, title or image), each arm's showings and profit per showing with an
 * interval, and whether choosing the arm per person beats one arm for everybody. Stored evidence (`scripts/experiments_evidence.py`), simulated showings.
 */
function Experiments() {
  usePagePanel(experimentsPanel(), {
    title: "Experiments",
    description: "A/B tests on how a product is shown: its offer, title or image, and whether choosing per person pays.",
    breadcrumb: "Operate › Experiments",
  });
  const [data, setData] = useState<ExperimentsData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [chosen, setChosen] = useUrlState("exp", "");

  useEffect(() => { apiFetch<ExperimentsData>("/api/experiments").then(setData).catch((e) => setError(String(e))); }, []);
  if (error) return <ErrorState title="Couldn't load the experiments" message={error} command="./do experiments-evidence" />;
  if (!data) return <div className="card" style={{ height: 160, background: "var(--border-light)" }} />;
  const selected = data.experiments.find((e) => e.experiment_id === chosen) ?? data.experiments[0];

  return (
    <div className="fade-in">
      <div className="page-header">
        <div className="page-title">Experiments</div>
        <div className="page-desc">
          A shop chooses how a product is shown: its price or offer, its title, its image. Each experiment shows two arms at random and counts what each earns per
          showing, with an interval, so a difference is not mistaken for luck. Then it asks whether choosing the arm <strong>for each person</strong> earns more than one arm for everybody.
          The showings are simulated, {data.months[0]} to {data.months[data.months.length - 1]}, and apart from the order data: a purchase here is not an order.
        </div>
      </div>
      <div className="workbench">
        <ExperimentList experiments={data.experiments} selected={selected.experiment_id} onSelect={setChosen} />
        <div style={{ display: "grid", gap: 12, minWidth: 0 }}>
          <ExperimentDetail e={selected} />
          <PersonalChoice kind={selected.kind} result={data.per_person[selected.kind]} arms={ARMS[selected.kind]} />
        </div>
      </div>
    </div>
  );
}

export default function ExperimentsPage() {
  return <Suspense fallback={null}><Experiments /></Suspense>;
}
