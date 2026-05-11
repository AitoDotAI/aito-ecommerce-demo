"use client";

import ScaffoldStub from "@/components/shell/ScaffoldStub";
import { recommendationsPanel } from "@/lib/panel-content";
import { usePagePanel } from "@/components/shell/ShellState";

export default function RecommendationsPage() {
  usePagePanel(recommendationsPanel(), {
    title: "For You",
    description:
      "Personalised product tiles for the selected customer. Switching the " +
      "customer-switcher pill flips the entire grid in < 300 ms.",
    breadcrumb: "For You",
  });

  return (
    <ScaffoldStub
      view="recommendations"
      step={7}
      blurb="Personalised tile grid for a selected customer, with a customer-switcher pill bar to flip context live (Maija / Olli / Saara). _recommend with goal: probability of purchase and where: customer profile."
    />
  );
}
