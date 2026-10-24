import type { UciBoughtTogether } from "@/lib/types";

/**
 * What is ordered with a product: the `_relate` over the training invoices'
 * codes. A lift of 3× means the code is on three times as many invoices
 * holding the chosen product as on invoices overall.
 */
export default function BoughtTogetherCard({ options, code, onPick, data }: {
  options: Array<{ code: string; description: string }>;
  code: string;
  onPick: (code: string) => void;
  data: UciBoughtTogether | null;
}) {
  return (
    <div className="card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <div className="card-title">Bought together</div>
        <select id="uci-product-picker" className="search-input" value={code}
                style={{ paddingLeft: 12, width: "auto", maxWidth: "100%" }}
                onChange={(e) => onPick(e.target.value)}>
          {options.map((o) => <option key={o.code} value={o.code}>{o.description}</option>)}
        </select>
      </div>
      <div className="card-sub" style={{ margin: "4px 0 12px" }}>
        {data
          ? `Codes on invoices holding ${data.product.description} (${data.invoices_with_product.toLocaleString("en-GB")} invoices before 1 Sep 2011), by lift`
          : "Loading…"}
      </div>
      {data && data.bought_with.length === 0 && (
        <div className="card-sub">No code shares enough of its invoices to call.</div>
      )}
      {data?.bought_with.map((b) => (
        <div key={b.code} style={{ display: "flex", justifyContent: "space-between", gap: 12, padding: "5px 0", fontSize: 13 }}>
          <span>
            {b.description}
            <span style={{ color: "var(--text-muted)", fontSize: 11 }}> · {b.code} · on {b.shared_invoices.toLocaleString("en-GB")} of them</span>
          </span>
          <strong style={{ color: b.lift > 1 ? "var(--green)" : "var(--red)", whiteSpace: "nowrap" }}>{b.lift.toFixed(1)}×</strong>
        </div>
      ))}
    </div>
  );
}
