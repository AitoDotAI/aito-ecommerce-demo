import { fmtEur } from "@/lib/api";
import type { KpiId, SegmentView, TreeFigures } from "@/lib/customer-profiles";

/** The figures the tree compares segments by, and the trend graph follows: what each is called, how it is written, and how it changes. */
export interface KpiSpec {
  id: KpiId; label: string; trendNote: string; format: (n: number) => string;
  /** How the change over the last three months is written: a percentage of the figure, or points for a score. */
  change: (n: number) => string;
}

const percent = (n: number) => `${n > 0 ? "+" : n < 0 ? "−" : ""}${Math.abs(Math.round(n * 100))} %`;

export const KPIS: KpiSpec[] = [
  { id: "customers", label: "Customers", trendNote: "customers who ordered in the month", format: (n) => n.toLocaleString("en-GB"), change: percent },
  { id: "orders", label: "Purchases", trendNote: "orders placed in the month", format: (n) => n.toLocaleString("en-GB"), change: percent },
  { id: "revenue_eur", label: "Revenue", trendNote: "price paid on the lines kept, per month", format: (n) => fmtEur(n), change: percent },
  { id: "profit_per_customer_eur", label: "Profit per customer", trendNote: "gross profit per customer who ordered in the month (before action costs)",
    format: (n) => fmtEur(n), change: percent },
  { id: "nps", label: "NPS", trendNote: "NPS of the answers in the six months up to the month; blank where there are fewer than 30",
    format: (n) => `${n > 0 ? "+" : ""}${n}`, change: (n) => `${n > 0 ? "+" : n < 0 ? "−" : ""}${Math.abs(n)} points` },
];

export const kpiSpec = (id: KpiId): KpiSpec => KPIS.find((k) => k.id === id)!;

/** The figure a tree row or the selected segment has for a KPI (null where the data does not give one). */
export function figureOf(id: KpiId, figures: TreeFigures): number | null {
  return figures[id];
}

/** The selected segment's own figures, in the same shape as a tree row's. */
export function figuresOf(view: SegmentView): TreeFigures | null {
  if (view.too_small || !view.trend || !view.segment || !view.feedback) return null;
  const sum = (xs: number[]) => xs.reduce((a, b) => a + b, 0);
  return { customers: view.customers, orders: sum(view.trend.selected.orders), revenue_eur: Math.round(sum(view.trend.selected.revenue_eur) * 100) / 100,
           profit_per_customer_eur: view.segment.profit_per_customer_eur ?? null, nps: view.feedback.selected.nps };
}
