"use client";

import ScaffoldStub from "@/components/shell/ScaffoldStub";
import { productFillingPanel } from "@/lib/panel-content";
import { usePagePanel } from "@/components/shell/ShellState";

export default function ProductFillingPage() {
  usePagePanel(productFillingPanel(), {
    title: "Product Filling",
    description:
      "An incomplete product card with five missing fields, filled in by Aito " +
      "with confidence chips — multi-field `_predict` for catalog enrichment.",
    breadcrumb: "Product Filling",
  });

  return (
    <ScaffoldStub
      view="product-filling"
      step={10}
      blurb="Incomplete product card on the left (missing category, weight, tax_class, dietary, …); on the right, the same five fields filled in by Aito with confidence chips."
    />
  );
}
