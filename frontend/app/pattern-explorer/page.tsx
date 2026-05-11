"use client";

import ScaffoldStub from "@/components/shell/ScaffoldStub";
import { patternExplorerPanel } from "@/lib/panel-content";
import { usePagePanel } from "@/components/shell/ShellState";

export default function PatternExplorerPage() {
  usePagePanel(patternExplorerPanel(), {
    title: "Pattern Explorer",
    description:
      "Ad-hoc `_relate` query builder: pick a field + value and see which " +
      "other attributes correlate unusually.",
    breadcrumb: "Pattern Explorer",
  });

  return (
    <ScaffoldStub
      view="pattern-explorer"
      step={9}
      blurb="_relate query builder with target field, conditions, threshold, and a results table sorted by lift. The Aito panel shows the discovery query and how to read $why-style outputs."
    />
  );
}
