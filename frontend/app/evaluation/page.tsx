"use client";

import ScaffoldStub from "@/components/shell/ScaffoldStub";
import { evaluationPanel } from "@/lib/panel-content";
import { usePagePanel } from "@/components/shell/ShellState";

export default function EvaluationPage() {
  usePagePanel(evaluationPanel(), {
    title: "Evaluation",
    description:
      "Pass/fail rows per prediction model, accuracy bands, last-evaluated " +
      "timestamps. Aito's `_evaluate` lets the demo be honest — at least one " +
      "model deliberately fails its threshold.",
    breadcrumb: "Evaluation",
  });

  return (
    <ScaffoldStub
      view="evaluation"
      step={10}
      blurb="Pass/fail rows for each prediction model (recommendations, smart search, product filling, return risk) with accuracy bands and last-evaluated timestamps. _evaluate endpoint + methodology."
    />
  );
}
