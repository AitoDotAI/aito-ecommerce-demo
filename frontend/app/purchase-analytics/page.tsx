"use client";

import ScaffoldStub from "@/components/shell/ScaffoldStub";
import { purchaseAnalyticsPanel } from "@/lib/panel-content";
import { usePagePanel } from "@/components/shell/ShellState";

export default function PurchaseAnalyticsPage() {
  usePagePanel(purchaseAnalyticsPanel(), {
    title: "Purchase Analytics",
    description:
      "Month-over-month bars, top products, category breakdown, AOV by segment " +
      "— `_search` + aggregations, no pre-built dashboards.",
    breadcrumb: "Purchase Analytics",
  });

  return (
    <ScaffoldStub
      view="purchase-analytics"
      step={9}
      blurb="Month-over-month bars, top products, category breakdown, AOV by segment. The Aito panel shows the _search + aggregation queries and the underlying schema."
    />
  );
}
