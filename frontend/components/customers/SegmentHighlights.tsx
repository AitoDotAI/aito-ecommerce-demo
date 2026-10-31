"use client";

import Link from "next/link";

import { fmtEur } from "@/lib/api";
import { ACTION_TITLE, TRAIT_TITLE, definitionOf, type ProfilesSummary, type SegmentView } from "@/lib/customer-profiles";

interface Item { tone: "good" | "bad" | "note"; text: string }

/** What the data lets the shop do for this segment: only differences larger than their margins are listed. */
export function actionableItems(view: SegmentView): Item[] {
  const items: Item[] = [];
  for (const [action, cell] of Object.entries(view.response?.actions ?? {})) {
    const name = ACTION_TITLE[action];
    if (cell.profit_clear && cell.profit_lift_eur !== null && cell.profit_lift_eur > 0) {
      items.push({ tone: "good", text: `${name} pays: ${fmtEur(cell.profit_lift_eur, 2)} more profit per action than no action (±${cell.profit_margin_eur}).` });
    } else if (cell.profit_clear && cell.profit_lift_eur !== null && cell.profit_lift_eur < 0) {
      items.push({ tone: "bad", text: `${name} loses money: ${fmtEur(cell.profit_lift_eur, 2)} per action against no action (±${cell.profit_margin_eur}).` });
    } else if (cell.clear && cell.lift_points !== null && cell.lift_points > 0) {
      items.push({ tone: "note", text: `${name} lifts orders by ${cell.lift_points} points, but not clearly their profit.` });
    }
  }
  const acquired = view.conditions.length === 0 ? [] : [...(view.acquisition?.source ?? [])].filter((r) => r.clear)
    .sort((x, y) => Math.abs(y.points ?? 0) - Math.abs(x.points ?? 0));
  for (const r of acquired.slice(0, 2)) {
    const channelProfit = r.profit_per_customer_all_eur === null ? "" : `; customers from it earn ${fmtEur(r.profit_per_customer_all_eur)} each on average`;
    items.push({ tone: "note", text: `${(r.points ?? 0) > 0 ? "More" : "Fewer"} come through ${r.value.replace("_", " ")} than of the other customers (${(r.points ?? 0) > 0 ? "+" : ""}${r.points} points)${channelProfit}.` });
  }
  for (const r of (view.relations ?? []).filter((x) => x.clear && x.points > 0).slice(0, 3)) {
    items.push({ tone: "note", text: `More often ${TRAIT_TITLE[r.then.trait].toLowerCase()}: ${r.then.value} (+${r.points} points).` });
  }
  if (items.length === 0) {
    items.push({ tone: "note", text: view.conditions.length === 0
      ? "No action clearly pays or loses here; the data cannot separate them from chance."
      : "Nothing clears its margin for this segment: the data cannot tell whether any action pays." });
  }
  return items;
}

const COLOUR = { good: "var(--aito-teal)", bad: "var(--cta)", note: "var(--text-muted)" } as const;

/** The first tab: what the data lets the shop do for this segment, and who the customers are in words. */
export default function SegmentHighlights({ summary, view }: { summary: ProfilesSummary; view: SegmentView }) {
  const items = actionableItems(view);
  return (
    <div className="card">
      <div style={{ fontWeight: 600, marginBottom: 6 }}>What to do</div>
      {items.map((item, i) => (
        <div key={i} style={{ display: "flex", gap: 8, fontSize: 13, lineHeight: 1.5, margin: "4px 0" }}>
          <span style={{ width: 8, height: 8, borderRadius: "50%", background: COLOUR[item.tone], marginTop: 6, flex: "none" }} />
          <span>{item.text}</span>
        </div>
      ))}
      <div style={{ fontWeight: 600, margin: "14px 0 6px" }}>Who they are</div>
      {view.conditions.length === 0
        ? <div style={{ fontSize: 13, lineHeight: 1.5 }}>{summary.definitions.all}</div>
        : view.conditions.map((c) => <div key={c} style={{ fontSize: 13, lineHeight: 1.5 }}>{definitionOf(summary, c)}</div>)}
      <div className="card-sub" style={{ marginTop: 10 }}>
        Observed in simulated data; a difference does not prove the action caused it. In the other views: <Link href="/acquisition/">Acquisition</Link> · <Link href="/retention/">Retention</Link> · <Link href="/product/">Product</Link> ·{" "}
        <Link href="/shopkeeper/?run=winback">the Shopkeeper&apos;s win-back run</Link>
      </div>
    </div>
  );
}
