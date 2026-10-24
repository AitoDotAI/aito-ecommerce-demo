import Link from "next/link";

import { fmtEur } from "@/lib/api";
import type { OverviewHeadline, OverviewHousehold, OverviewMonth, OverviewTopProduct } from "@/lib/types";


export function KpiCard({ label, value, change, accent }: {
  label: string; value: string; change?: string | null; accent: string;
}) {
  return (
    <div className={`kpi-card ${accent}`}>
      <div className="kpi-label">{label}</div>
      <div className="kpi-val">{value}</div>
      {change && <div className="kpi-change">{change}</div>}
    </div>
  );
}

/** One owner view's headline: the decision, with its number, as a link. */
export function HeadlineCard({ h }: { h: OverviewHeadline }) {
  return (
    <Link href={h.href} className="card evidence-entry" style={{ marginBottom: 0 }}>
      <div className="card-sub" style={{ fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em", fontSize: 11 }}>
        {h.view} →
      </div>
      <div style={{ fontSize: 14, fontWeight: 600, margin: "6px 0 4px", color: "var(--text)" }}>
        {h.headline}
      </div>
      <div className="card-sub">{h.detail}</div>
    </Link>
  );
}

export function MonthlyBars({ months }: { months: OverviewMonth[] }) {
  const most = Math.max(1, ...months.map((m) => m.revenue_eur));
  return (
    <div style={{ maxHeight: 360, overflowY: "auto" }}>
      {months.slice().reverse().map((m) => (
        <div className="hbar-row" key={m.month}>
          <div className="hbar-label" style={{ fontFamily: "var(--mono)", fontSize: 12, width: 70 }}>{m.month}</div>
          <div className="hbar-wrap">
            <div className="hbar" style={{ width: `${(m.revenue_eur / most) * 100}%`, background: "var(--cta)" }} />
          </div>
          <div className="hbar-val" style={{ width: 150 }}>
            {fmtEur(m.revenue_eur)} · {m.orders.toLocaleString("en-US")}
          </div>
        </div>
      ))}
    </div>
  );
}

export function BestSellers({ products }: { products: OverviewTopProduct[] }) {
  const most = Math.max(1, ...products.map((p) => p.units));
  return (
    <>
      {products.map((p) => (
        <div className="hbar-row" key={p.sku}>
          <div className="hbar-label" style={{ width: 200 }}>
            <Link href={`/product/?sku=${p.sku}`} style={{ fontSize: 12, fontWeight: 600 }}>{p.name}</Link>
            <div style={{ fontSize: 10, color: "var(--text-muted)" }}>{p.sku} · {p.pet_type} · {p.category}</div>
          </div>
          <div className="hbar-wrap">
            <div className="hbar" style={{ width: `${(p.units / most) * 100}%`, background: "var(--green)" }} />
          </div>
          <div className="hbar-val">{p.units}</div>
        </div>
      ))}
    </>
  );
}

export function HouseholdCards({ households }: { households: OverviewHousehold[] }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {households.map((h) => (
        <div key={h.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: 10,
                                 background: "var(--bg)", borderRadius: 8 }}>
          <span style={{ fontSize: 20 }} aria-hidden="true">{h.emoji}</span>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, fontWeight: 600 }}>{h.label}</div>
            <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
              {h.customers.toLocaleString("en-US")} customers ({h.share_pct} %) · avg {fmtEur(h.avg_basket_eur)} / order
            </div>
          </div>
          {h.pill_text && <span className={`pill pill-${h.pill_tone}`}>{h.pill_text}</span>}
        </div>
      ))}
    </div>
  );
}

/** "+12 % on the 12 months before", or nothing when the data doesn't hold all 12. */
export function changeOnBefore(now: number, before: number, monthsBefore: number): string | null {
  if (monthsBefore < 12 || before === 0) return null;
  const change = (now / before - 1) * 100;
  return `${change >= 0 ? "+" : ""}${change.toFixed(0)} % on the 12 months before`;
}
