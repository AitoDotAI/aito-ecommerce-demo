"use client";

import ScaffoldStub from "@/components/shell/ScaffoldStub";
import { smartSearchPanel } from "@/lib/panel-content";
import { usePagePanel } from "@/components/shell/ShellState";

export default function SmartSearchPage() {
  usePagePanel(smartSearchPanel(), {
    title: "Smart Search",
    description:
      "Free-text search re-ranked by purchase probability — the cat food drops " +
      "from rank 1 to rank 6 for a large-breed dog owner.",
    breadcrumb: "Smart Search",
  });

  return (
    <ScaffoldStub
      view="smart-search"
      step={6}
      blurb="Side-by-side standard vs. predictive results for the query 'food' with a large-breed dog-owner context. Cat food drops from rank 1 to rank 6 because the customer has never bought cat products."
    />
  );
}
