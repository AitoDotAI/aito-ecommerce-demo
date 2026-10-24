import type { UciDraftOrder } from "@/lib/types";
import { fmtDate, fmtGbp } from "./format";

/**
 * Aito's draft of a buyer's next order: the top codes of one `_predict`,
 * each with Aito's probability and its last price, and a ✓ where the buyer
 * really ordered that code next (their first invoice after the cutoff,
 * which Aito never saw).
 */
export default function DraftTable({ draft }: { draft: UciDraftOrder }) {
  return (
    <div className="card">
      <div className="card-title">Aito&apos;s draft of their next order</div>
      <div className="card-sub" style={{ marginBottom: 12 }}>
        Customer {draft.customer_id} · {draft.prior_invoices} earlier{" "}
        {draft.prior_invoices === 1 ? "order" : "orders"} before 1 Sep 2011
        {draft.next_order_date && <> · ordered next on {fmtDate(draft.next_order_date)}, {draft.next_order_size} products</>}
      </div>
      <table className="data-table" style={{ tableLayout: "auto" }}>
        <thead>
          <tr>
            <th style={{ padding: "8px 6px" }}>Product</th>
            <th style={{ padding: "8px 6px", textAlign: "right" }}>Aito</th>
            <th style={{ padding: "8px 6px", textAlign: "right" }}>Last price</th>
            <th style={{ padding: "8px 6px", textAlign: "center" }} title="In their next order">Next</th>
          </tr>
        </thead>
        <tbody>
          {draft.lines.map((line) => (
            <tr key={line.code}>
              <td style={{ padding: "8px 6px" }}>
                <div style={{ fontSize: 13 }}>{line.description}</div>
                <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{line.code}</div>
              </td>
              <td style={{ padding: "8px 6px", textAlign: "right", whiteSpace: "nowrap" }}>
                {(line.probability * 100).toFixed(1)} %
              </td>
              <td style={{ padding: "8px 6px", textAlign: "right", whiteSpace: "nowrap" }}>
                {fmtGbp(line.last_price_gbp)}
              </td>
              <td style={{ padding: "8px 6px", textAlign: "center", color: "var(--green)", fontWeight: 700 }}
                  aria-label={line.ordered_next ? "in their next order" : "not in their next order"}>
                {line.ordered_next ? "✓" : ""}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 8, marginTop: 12, fontSize: 13 }}>
        <span>
          Draft value <strong>{fmtGbp(draft.draft_value_gbp)}</strong>{" "}
          <span style={{ color: "var(--text-muted)" }}>at last prices, one of each</span>
        </span>
        <span style={{ color: draft.top_suggestion_ordered ? "var(--green)" : "var(--text-2)" }}>
          Top suggestion {draft.top_suggestion_ordered ? "was" : "was not"} in their next order
        </span>
      </div>
    </div>
  );
}
