"use client";

import type { ProductMonth } from "@/lib/types";
import { BAND_LABEL, monthLabel, shortMonth } from "./labels";

/** The month's events, each a symbol and words: identity is never color alone. */
const EVENTS: Array<{ symbol: string; label: string; happened: (m: ProductMonth, prev?: ProductMonth) => string | null }> = [
  { symbol: "%", label: "On offer", happened: (m) => (m.discount_band !== "none" ? BAND_LABEL[m.discount_band] : null) },
  { symbol: "↑", label: "Price rise", happened: (m, prev) =>
      (m.price_change === "rise" && prev?.price_change !== "rise" ? `list price to €${m.list_price_eur.toFixed(2)}` : null) },
  { symbol: "R", label: "Rival launched", happened: (m, prev) => (m.rival_launched && !prev?.rival_launched ? "a rival launched" : null) },
  { symbol: "N", label: "New", happened: (m) => (m.age === "new" ? "new product" : null) },
  { symbol: "★", label: "Stars changed", happened: (m, prev) =>
      (prev && m.rating_band !== prev.rating_band ? `stars ${prev.rating_band} → ${m.rating_band}` : null) },
];

/**
 * Units per month, with the product's state marked under each bar: offers,
 * a price rise, a rival's launch, being new, a change of stars, and the
 * month's reviews. The month asked about is outlined.
 */
export default function ProductMonths({ months, selected }: { months: ProductMonth[]; selected: string }) {
  const top = Math.max(1, ...months.map((m) => m.units_sold));
  const events = months.map((m, i) => EVENTS.map((e) => e.happened(m, months[i - 1])));

  return (
    <div className="card">
      <div className="page-title" style={{ fontSize: 16, margin: "0 0 4px" }}>Units per month, and what happened</div>
      <div className="card-sub" style={{ marginBottom: 12 }}>
        From monthly_sales and product_states. Hover a month for its numbers.
      </div>
      <div role="img" aria-label={`Units sold per month, ${months[0]?.month} to ${months[months.length - 1]?.month}`}
           style={{ display: "flex", alignItems: "flex-end", gap: 2, height: 140 }}>
        {months.map((m, i) => (
          <div key={m.month} title={tooltip(m, events[i])}
               style={{ flex: 1, height: "100%", display: "flex", flexDirection: "column", justifyContent: "flex-end",
                        outline: m.month === selected ? "2px solid var(--text-2)" : undefined, outlineOffset: 1 }}>
            <div style={{ fontSize: 10, textAlign: "center", color: "var(--text-muted)" }}>{m.units_sold}</div>
            <div style={{ height: `${(m.units_sold / top) * 100}%`, minHeight: 1, background: "var(--cta)",
                          borderRadius: "4px 4px 0 0" }} />
          </div>
        ))}
      </div>
      {EVENTS.map((e, row) => events.some((ev) => ev[row]) && (
        <div key={e.label} style={{ display: "flex", gap: 2, marginTop: 2 }} aria-hidden="true">
          {months.map((m, i) => (
            <div key={m.month} style={{ flex: 1, textAlign: "center", fontSize: 11, lineHeight: "16px",
                                        color: "var(--text-2)", background: events[i][row] ? "var(--border-light)" : undefined,
                                        borderRadius: 3 }}>
              {events[i][row] ? e.symbol : ""}
            </div>
          ))}
        </div>
      ))}
      <div style={{ display: "flex", gap: 2, marginTop: 2 }} aria-hidden="true">
        {months.map((m) => (
          <div key={m.month} style={{ flex: 1, textAlign: "center", fontSize: 10, color: "var(--text-muted)" }}>
            {m.reviews > 0 ? m.reviews : ""}
          </div>
        ))}
      </div>
      <div className="card-sub" style={{ display: "flex", justifyContent: "space-between", marginTop: 4 }}>
        <span>{shortMonth(months[0].month)}</span><span>{shortMonth(months[months.length - 1].month)}</span>
      </div>
      <div className="card-sub" style={{ marginTop: 8 }}>
        {EVENTS.map((e) => `${e.symbol} ${e.label.toLowerCase()}`).join(" · ")} · bottom row: reviews written that month
      </div>
      <ul style={{ margin: "10px 0 0", paddingLeft: 18, fontSize: 13 }}>
        {months.map((m, i) => events[i].some(Boolean) && (
          <li key={m.month}>
            <strong>{monthLabel(m.month)}</strong>: {events[i].filter(Boolean).join(", ")} · {m.units_sold} units
            at €{m.price_eur.toFixed(2)}
          </li>
        ))}
      </ul>
    </div>
  );
}

function tooltip(m: ProductMonth, events: Array<string | null>): string {
  const what = events.filter(Boolean).join(", ");
  return `${monthLabel(m.month)}: ${m.units_sold} units at €${m.price_eur.toFixed(2)} · stars ${m.rating_band}` +
    ` · ${m.reviews} reviews${what ? ` · ${what}` : ""}`;
}
