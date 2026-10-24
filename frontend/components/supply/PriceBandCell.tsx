import { fmtEur } from "@/lib/api";
import type { PriceBand } from "@/lib/types";

/**
 * A SKU's list price against the band it actually sold at (mean ± 1.5σ of
 * its realised prices, `src/price_bands.py`). An outlier is flagged only on
 * enough observations for a band to mean anything.
 */
export default function PriceBandCell({ price }: { price: PriceBand | null }) {
  if (!price) return <span className="card-sub">no sales prices</span>;
  const title =
    `Usually sold at ${fmtEur(price.band_low_eur, 2)}–${fmtEur(price.band_high_eur, 2)} ` +
    `(mean ${fmtEur(price.mean_price_eur, 2)}, ${price.observations} months)`;
  return (
    <span title={title} style={{ whiteSpace: "nowrap" }}>
      {fmtEur(price.list_price_eur, 2)}
      {price.outlier && (
        <span className="pill pill-amber" style={{ marginLeft: 6, fontSize: 10 }}>
          {price.list_price_eur > price.band_high_eur ? "above band" : "below band"}
        </span>
      )}
      <div style={{ fontSize: 10.5, color: "var(--text-muted)" }}>
        usually {fmtEur(price.band_low_eur, 2)}–{fmtEur(price.band_high_eur, 2)}
      </div>
    </span>
  );
}
