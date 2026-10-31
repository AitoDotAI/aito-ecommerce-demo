"use client";

import Link from "next/link";
import { useRef } from "react";

import { fmtEur } from "@/lib/api";
import { ACTION_TITLE, TRAIT_TITLE, definitionOf, type ProfilesSummary, type SegmentView } from "@/lib/customer-profiles";
import PreferenceGraph from "@/components/customers/PreferenceGraph";

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

/** The top left: who the selected customers are, in words, and what can be done about it. */
export default function SegmentProfile({ summary, view }: { summary: ProfilesSummary; view: SegmentView }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const items = actionableItems(view);
  const rankings = Object.values(view.ranking ?? {});
  const title = view.conditions.length === 0 ? "Everyone profiled" : view.conditions.map((c) => c.split(":").slice(1).join(":")).join(" · ");
  return (
    <div className="card" style={{ borderTop: "3px solid var(--aito-teal)" }}>
      <div className="card-sub">{view.conditions.length === 0 ? "No condition ticked" : view.conditions.map((c) => TRAIT_TITLE[c.split(":")[0]]).join(" · ")}</div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, margin: "2px 0 6px" }}>
        <div className="page-title" style={{ fontSize: 24, margin: 0 }}>{title}</div>
        <button aria-label="Where this segment sits in the preference ranking" title="Where do they sit in the ranking of what customers prefer?"
                onClick={() => dialog.current?.showModal()} style={{ cursor: "pointer", width: 22, height: 22, borderRadius: "50%", border: "1px solid var(--border)",
                  background: "transparent", color: "var(--text)", font: "inherit", fontSize: 13, lineHeight: 1, flex: "none" }}>?</button>
      </div>
      {view.conditions.length === 0
        ? <div style={{ fontSize: 14, lineHeight: 1.55 }}>{summary.definitions.all}</div>
        : view.conditions.map((c) => <div key={c} style={{ fontSize: 14, lineHeight: 1.55 }}>{definitionOf(summary, c)}</div>)}
      <div className="card-sub" style={{ marginTop: 6 }}>
        {view.customers.toLocaleString("en-GB")} customers, {Math.round((view.customers / summary.profiled) * 100)} % of those profiled.
      </div>
      <div style={{ fontWeight: 600, margin: "14px 0 6px" }}>What to do</div>
      {items.map((item, i) => (
        <div key={i} style={{ display: "flex", gap: 8, fontSize: 13, lineHeight: 1.5, margin: "4px 0" }}>
          <span style={{ width: 8, height: 8, borderRadius: "50%", background: COLOUR[item.tone], marginTop: 6, flex: "none" }} />
          <span>{item.text}</span>
        </div>
      ))}
      <div className="card-sub" style={{ marginTop: 10 }}>
        Observed in simulated data; a difference does not prove the action caused it. In the other views: <Link href="/acquisition/">Acquisition</Link> · <Link href="/retention/">Retention</Link> · <Link href="/product/">Product</Link> ·{" "}
        <Link href="/shopkeeper/?run=winback">the Shopkeeper&apos;s win-back run</Link>
      </div>
      <dialog ref={dialog} onClick={(e) => { if (e.target === dialog.current) dialog.current?.close(); }}
              style={{ width: "min(640px, 94vw)", border: "1px solid var(--border)", borderRadius: 8, padding: 16, background: "var(--bg)", color: "var(--text)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 8 }}>
          <div className="card-title" style={{ margin: 0 }}>Where {title.toLowerCase()} sit in what customers prefer</div>
          <button className="btn btn-ghost" style={{ padding: "2px 10px", fontSize: 12 }} onClick={() => dialog.current?.close()}>Close</button>
        </div>
        {rankings.length === 0 && (
          <div className="card-sub" style={{ lineHeight: 1.5 }}>
            Tick a way of shopping (buys on offer, prices they pick, ratings they pick) to see where it sits in the ranking of that preference.
            Margin, pets and diets are not a share of what a customer bought, so they have no ranking.
          </div>
        )}
        {rankings.map((ranked) => (
          <div key={ranked.label} style={{ marginBottom: 16 }}>
            <PreferenceGraph ranked={ranked} selected={view.key} segmentShare={view.customers / summary.profiled} />
          </div>
        ))}
      </dialog>
    </div>
  );
}
