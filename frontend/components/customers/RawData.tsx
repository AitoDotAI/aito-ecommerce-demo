"use client";

import { useEffect, useState } from "react";

import { apiFetch, fmtEur } from "@/lib/api";

const TABS = [{ id: "sales", label: "Sales by product" }, { id: "orders", label: "Orders" }, { id: "feedback", label: "Feedback" }] as const;
type TabId = (typeof TABS)[number]["id"];
const PAGE = 25;

type Row = Record<string, string | number | boolean | null>;
interface Page { tab: TabId; total: number; rows: Row[]; too_small: boolean }

const eur = (v: Row[string]) => fmtEur(Number(v));
const text = (v: Row[string]) => (v === null ? "" : String(v));

const COLUMNS: Record<TabId, { key: string; label: string; right?: boolean; format?: (v: Row[string]) => string }[]> = {
  sales: [
    { key: "product", label: "Product" }, { key: "brand", label: "Brand" }, { key: "category", label: "Category" },
    { key: "units", label: "Units", right: true }, { key: "returned_units", label: "Returned", right: true },
    { key: "revenue_eur", label: "Revenue", right: true, format: eur }, { key: "customers", label: "Customers", right: true },
  ],
  orders: [
    { key: "order", label: "Order" }, { key: "month", label: "Month" }, { key: "total_eur", label: "Total", right: true, format: eur },
    { key: "lines", label: "Lines", right: true }, { key: "returned_lines", label: "Returned lines", right: true },
  ],
  feedback: [
    { key: "month", label: "Month" }, { key: "kind", label: "Kind" }, { key: "product", label: "Product", format: text },
    { key: "rating", label: "Stars / score", right: true }, { key: "topic", label: "Topic" }, { key: "text", label: "Text", format: text },
  ],
};

/**
 * The raw rows behind the selection (ADR 0055), full width under both panes: sales by product, orders, and the individual reviews and NPS answers
 * of the selected customers, only the months of the chosen period when there is one. A row says what happened and never who it happened to.
 */
export default function RawData({ conditions, from, to }: { conditions: string[]; from: string; to: string }) {
  const [tab, setTab] = useState<TabId>("sales");
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<Page | null>(null);
  const [error, setError] = useState<string | null>(null);
  const selection = JSON.stringify([conditions, from, to, tab]);

  useEffect(() => { setOffset(0); }, [selection]);
  useEffect(() => {
    const parts = [`tab=${tab}`, `limit=${PAGE}`, `offset=${offset}`, ...conditions.map((c) => `c=${encodeURIComponent(c)}`)];
    if (from && to) parts.push(`start=${from}`, `end=${to}`);
    apiFetch<Page>(`/api/customer-profiles/rows?${parts.join("&")}`).then((p) => { setPage(p); setError(null); }).catch((e) => setError(String(e)));
    // `selection` stands for the conditions, the period and the tab, which the request reads.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selection, offset]);

  const columns = COLUMNS[tab];
  const last = page ? Math.min(offset + PAGE, page.total) : 0;
  return (
    <div className="card" style={{ marginTop: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
        <div className="card-title" style={{ margin: 0 }}>The data behind it{from && to ? `, ${from} … ${to}` : ""}</div>
        <div role="tablist" aria-label="Raw data" style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {TABS.map((t) => (
            <button key={t.id} role="tab" aria-selected={tab === t.id} className={`toggle-btn${tab === t.id ? " active" : ""}`} onClick={() => setTab(t.id)}
                    style={{ width: "auto", height: "auto", padding: "4px 12px", whiteSpace: "nowrap", fontSize: 13 }}>{t.label}</button>
          ))}
        </div>
      </div>
      {error && <div className="card-sub" style={{ marginTop: 8 }}>{error}</div>}
      {page && !page.too_small && (
        <>
          <div className="scroll-x">
            <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse", marginTop: 8 }}>
              <thead>
                <tr className="card-sub">
                  {columns.map((col) => <th key={col.key} style={{ textAlign: col.right ? "right" : "left", fontWeight: 500, padding: "2px 8px 2px 0" }}>{col.label}</th>)}
                </tr>
              </thead>
              <tbody>
                {page.rows.map((row, i) => (
                  <tr key={i} style={{ borderTop: "1px solid var(--border-light)", verticalAlign: "top" }}>
                    {columns.map((col) => (
                      <td key={col.key} style={{ textAlign: col.right ? "right" : "left", padding: "3px 8px 3px 0", ...(col.key === "text" ? { minWidth: 260 } : {}) }}>
                        {col.format ? col.format(row[col.key]) : String(row[col.key] ?? "")}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 8 }}>
            <span className="card-sub">{page.total === 0 ? "No rows in this period." : `Rows ${offset + 1}–${last} of ${page.total.toLocaleString("en-GB")}`}</span>
            <span style={{ display: "flex", gap: 6 }}>
              <button className="btn btn-ghost" style={{ padding: "2px 10px", fontSize: 12 }} disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</button>
              <button className="btn btn-ghost" style={{ padding: "2px 10px", fontSize: 12 }} disabled={last >= page.total} onClick={() => setOffset(offset + PAGE)}>Next</button>
            </span>
          </div>
          <div className="card-sub" style={{ marginTop: 4 }}>Rows of the customers who consented to profiling. A row says what happened, not who it happened to.</div>
        </>
      )}
    </div>
  );
}
