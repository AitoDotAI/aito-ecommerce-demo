import Link from "next/link";

import { fmtEur } from "@/lib/api";
import WhyPopover from "@/components/prediction/WhyPopover";
import type { SupplyMoverRow, SupplyPriceOutlier } from "@/lib/types";

/** The best sellers' forecasts beside their stock: where a stock-out would hurt most. */
export function TopMovers({ rows, month }: { rows: SupplyMoverRow[]; month: string }) {
  return (
    <table className="recent-table" style={{ width: "100%", fontSize: 12.5 }}>
      <thead>
        <tr>
          <th style={{ textAlign: "left" }}>Product</th>
          <th style={{ textAlign: "right" }}>Average<br /><span style={{ fontWeight: 400 }}>a month</span></th>
          <th style={{ textAlign: "right" }}>Last<br /><span style={{ fontWeight: 400 }}>month</span></th>
          <th style={{ textAlign: "right" }}>{month}<br /><span style={{ fontWeight: 400 }}>forecast</span></th>
          <th style={{ textAlign: "right" }}>Stock</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((m) => (
          <tr key={m.sku}>
            <td><Link href={`/product-insights/?sku=${encodeURIComponent(m.sku)}`}>{m.name}</Link></td>
            <td style={{ textAlign: "right" }}>{m.avg_monthly_units}</td>
            <td style={{ textAlign: "right" }}>{m.last_month_units}</td>
            <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
              <strong>{m.forecast_units}</strong>
              {m.why_explanation && (
                <span style={{ marginLeft: 4 }}>
                  <WhyPopover why={m.why_explanation} title={`${m.name}: ${m.forecast_units} units`} />
                </span>
              )}
            </td>
            <td style={{ textAlign: "right", color: m.current_stock < m.forecast_units ? "var(--red)" : undefined }}>
              {m.current_stock}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** List prices outside what the product usually sold at: worth a look before reordering at that price. */
export function PriceOutliers({ rows }: { rows: SupplyPriceOutlier[] }) {
  if (rows.length === 0) return <div className="card-sub">Every list price sits inside its band.</div>;
  return (
    <table className="recent-table" style={{ width: "100%", fontSize: 12.5 }}>
      <thead>
        <tr>
          <th style={{ textAlign: "left" }}>Product</th>
          <th style={{ textAlign: "right" }}>List price</th>
          <th style={{ textAlign: "right" }}>Usually sold at</th>
          <th style={{ textAlign: "right" }}>Off the band</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((o) => (
          <tr key={o.sku}>
            <td><Link href={`/product-insights/?sku=${encodeURIComponent(o.sku)}`}>{o.name}</Link></td>
            <td style={{ textAlign: "right" }}>{fmtEur(o.price.list_price_eur, 2)}</td>
            <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
              {fmtEur(o.price.band_low_eur, 2)}–{fmtEur(o.price.band_high_eur, 2)}
            </td>
            <td style={{ textAlign: "right", fontWeight: 700 }}>
              {o.above_band_pct > 0 ? "+" : ""}{o.above_band_pct} %
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
