"use client";

import ScaffoldStub from "@/components/shell/ScaffoldStub";
import { boughtTogetherPanel } from "@/lib/panel-content";
import { usePagePanel } from "@/components/shell/ShellState";

export default function BoughtTogetherPage() {
  usePagePanel(boughtTogetherPanel(), {
    title: "Bought Together",
    description:
      "Anchor product + four cross-sell tiles ranked by `_relate` lift. " +
      "Dog dry-food → dental treats runs at ≈ 2.7× baseline.",
    breadcrumb: "Bought Together",
  });

  return (
    <ScaffoldStub
      view="bought-together"
      step={8}
      blurb="Anchor product + four cross-sell tiles with lift scores. The Aito panel shows the _relate query and how lift is computed."
    />
  );
}
