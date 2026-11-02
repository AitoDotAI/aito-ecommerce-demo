"use client";

import { useEffect, useState } from "react";

import { apiFetch, fmtEur } from "@/lib/api";
import type { FeedbackFilter } from "@/components/customers/SegmentFeedbackPatterns";

const TABS = [{ id: "sales", label: "Sales by product" }, { id: "orders", label: "Orders" }, { id: "reviews", label: "Reviews" }, { id: "nps", label: "NPS answers" }] as const;
type TabId = (typeof TABS)[number]["id"];
const PAGE = 25;

type Row = Record<string, string | number | boolean | null>;
interface Page { tab: TabId; total: number; rows: Row[]; too_small: boolean }

const eur = (v: Row[string]) => fmtEur(Number(v));

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
  reviews: [
    { key: "month", label: "Month" }, { key: "product", label: "Product" }, { key: "stars", label: "Stars", right: true }, { key: "topic", label: "About" },
    { key: "replied", label: "Replied", format: (v) => (v ? "yes" : "no") }, { key: "text", label: "Review" },
  ],
  nps: [
    { key: "month", label: "Month" }, { key: "score", label: "Score (0–10)", right: true }, { key: "group", label: "Group" },
    { key: "also_wrote_a_negative_review", label: "Also wrote a negative review", format: (v) => (v ? "yes" : "no") },
    { key: "comment", label: "Comment", format: (v) => (v === null ? "" : String(v)) },
  ],
};

/**
 * The raw rows behind the selection (ADR 0055), full width under both panes: sales by product, orders, and the individual reviews and NPS answers
 * of the selected customers, only the months of the chosen period when there is one. A row says what happened and never who it happened to.
 */
export default function RawData({ conditions, from, to, pattern, onClearPattern }: { conditions: string[]; from: string; to: string; pattern: FeedbackFilter | null; onClearPattern: () => void }) {
  const [tab, setTab] = useState<TabId>("sales");
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<Page | null>(null);
  const [error, setError] = useState<string | null>(null);
  const selection = JSON.stringify([conditions, from, to, tab, pattern?.spec]);
  // Choosing a pattern shows the rows it is about: the reviews or the NPS answers, scrolled into view.
  useEffect(() => {
    if (!pattern) return;
    setTab(pattern.tab);
    document.getElementById("raw-data")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [pattern]);

  useEffect(() => { setOffset(0); }, [selection]);
  useEffect(() => {
    let current = true;   // a slower earlier answer must not replace a later one (the tab and the pattern change together)
    const parts = [`tab=${tab}`, `limit=${PAGE}`, `offset=${offset}`, ...conditions.map((c) => `c=${encodeURIComponent(c)}`)];
    if (from && to) parts.push(`start=${from}`, `end=${to}`);
    if (pattern && pattern.tab === tab) parts.push(`pattern=${encodeURIComponent(JSON.stringify(pattern.spec))}`);
    apiFetch<Page>(`/api/customer-profiles/rows?${parts.join("&")}`).then((p) => { if (current) { setPage(p); setError(null); } }).catch((e) => { if (current) setError(String(e)); });
    return () => { current = false; };
    // `selection` stands for the conditions, the period and the tab, which the request reads.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selection, offset]);

  const columns = COLUMNS[tab];
  const last = page ? Math.min(offset + PAGE, page.total) : 0;
  return (
    <div className="card" id="raw-data" style={{ marginTop: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
        <div className="card-title" style={{ margin: 0 }}>The data behind it{from && to ? `, ${from} … ${to}` : ""}</div>
        <div role="tablist" aria-label="Raw data" style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {TABS.map((t) => (
            <button key={t.id} role="tab" aria-selected={tab === t.id} className={`toggle-btn${tab === t.id ? " active" : ""}`} onClick={() => setTab(t.id)}
                    style={{ width: "auto", height: "auto", padding: "4px 12px", whiteSpace: "nowrap", fontSize: 13 }}>{t.label}</button>
          ))}
        </div>
      </div>
      {pattern && (
        <div style={{ marginTop: 8, display: "inline-flex", alignItems: "center", gap: 8, fontSize: 13, background: "rgba(0, 168, 150, 0.15)", borderRadius: 12, padding: "2px 4px 2px 12px" }}>
          <span>Only {pattern.spec.group === "stars" ? "reviews of 1–2 stars" : "detractors' answers"} with: <strong>{pattern.label}</strong></span>
          <button className="btn btn-ghost" style={{ padding: "0 8px", fontSize: 12 }} onClick={onClearPattern} aria-label="Clear the pattern filter">×</button>
        </div>
      )}
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
