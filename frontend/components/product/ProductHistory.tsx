"use client";

import type { ProductHistory as History } from "@/lib/types";
import ProductMonths from "./ProductMonths";
import { words } from "./labels";

const STEP_LABELS: Record<string, string> = {
  impressions: "Shown", clicked: "Clicked", added_to_cart: "Added to cart", purchased: "Purchased",
};

/**
 * Product › History (ADR 0028): what the data holds for this product. Its
 * months with their states, the funnel, the surfaces and the reviews.
 * Counts and rows, not estimates. Backend: src/product_history.py.
 */
export default function ProductHistory({ history, month }: { history: History; month: string }) {
  const top = history.funnel[0]?.count || 1;
  const topSurface = Math.max(1, ...history.surfaces.map((s) => s.impressions));
  const reviews = Object.values(history.ratings).reduce((a, b) => a + b, 0);
  const topRating = Math.max(1, ...Object.values(history.ratings));

  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: 16 }}>
      <ProductMonths months={history.months} selected={month} />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 16 }}>
        <Card title="Funnel" sub="Impressions → purchase, each rate of the step before">
          {history.funnel.map((s, i) => (
            <Bar key={s.step} label={STEP_LABELS[s.step]} value={s.count} share={s.count / top}
                 note={i === 0 ? "" : `${rate(s.count, history.funnel[i - 1].count)} of ${STEP_LABELS[history.funnel[i - 1].step].toLowerCase()}`} />
          ))}
        </Card>
        <Card title="By surface" sub="Where it was shown, and how often that ended in a purchase">
          {history.surfaces.map((s) => (
            <Bar key={s.surface} label={words(s.surface)} value={s.impressions} share={s.impressions / topSurface}
                 note={`${s.purchased} purchased (${rate(s.purchased, s.impressions)})`} />
          ))}
        </Card>
        <Card title="Reviews"
              sub={`${reviews} reviews · ${Object.entries(history.sentiments).map(([s, n]) => `${n} ${s}`).join(", ")}`}>
          {["5", "4", "3", "2", "1"].map((r) => (
            <Bar key={r} label={"★".repeat(Number(r))} value={history.ratings[r]} share={history.ratings[r] / topRating} note="" />
          ))}
        </Card>
      </div>
    </div>
  );
}

function Card({ title, sub, children }: { title: string; sub: string; children: React.ReactNode }) {
  return (
    <div className="card">
      <div className="page-title" style={{ fontSize: 16, margin: "0 0 4px" }}>{title}</div>
      <div className="card-sub" style={{ marginBottom: 12 }}>{sub}</div>
      {children}
    </div>
  );
}

function Bar({ label, value, share, note }: { label: string; value: number; share: number; note: string }) {
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
        <span>{label}</span>
        <span><strong>{value}</strong>{note && <span style={{ color: "var(--text-muted)", fontSize: 11 }}> · {note}</span>}</span>
      </div>
      <div style={{ height: 6, background: "var(--border-light)", borderRadius: 3 }}>
        <div style={{ width: `${share * 100}%`, height: "100%", background: "var(--cta)", borderRadius: 3 }} />
      </div>
    </div>
  );
}

function rate(part: number, whole: number): string {
  return whole === 0 ? "–" : `${Math.round((part / whole) * 100)}%`;
}
