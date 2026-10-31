"use client";

import Link from "next/link";

import { fmtEur } from "@/lib/api";
import { ACTION_TITLE, TRAIT_TITLE, definitionOf, findSegment, type ProfilesSummary } from "@/lib/customer-profiles";

interface Item { tone: "good" | "bad" | "note"; text: string }

/** What the data lets the shop do for this segment: only differences larger than their margins are listed. */
export function actionableItems(summary: ProfilesSummary, key: string): Item[] {
  const items: Item[] = [];
  const entry = summary.response[key];
  if (entry) {
    for (const [action, cell] of Object.entries(entry.actions)) {
      const name = ACTION_TITLE[action];
      if (cell.profit_clear && cell.profit_lift_eur !== null && cell.profit_lift_eur > 0) {
        items.push({ tone: "good", text: `${name} pays: ${fmtEur(cell.profit_lift_eur, 2)} more profit per customer-row than no action (±${cell.profit_margin_eur}).` });
      } else if (cell.profit_clear && cell.profit_lift_eur !== null && cell.profit_lift_eur < 0) {
        items.push({ tone: "bad", text: `${name} loses money: ${fmtEur(cell.profit_lift_eur, 2)} per customer-row against no action (±${cell.profit_margin_eur}).` });
      } else if (cell.clear && cell.lift_points !== null && cell.lift_points > 0) {
        items.push({ tone: "note", text: `${name} lifts orders by ${cell.lift_points} points, but not clearly their profit.` });
      }
    }
  }
  const [trait] = key.split(":");
  const related = summary.relations.filter((r) => `${r.if.trait}:${r.if.value}` === key && r.clear && r.points > 0).slice(0, 3);
  for (const r of related) {
    items.push({ tone: "note", text: `More often ${TRAIT_TITLE[r.then.trait].toLowerCase()}: ${r.then.value} (+${r.points} points).` });
  }
  if (items.length === 0) {
    items.push({ tone: "note", text: trait === "diets" || key === "all"
      ? "No action clearly pays or loses here; the data cannot separate them from chance."
      : "Nothing clears its margin for this segment: the data cannot tell whether any action pays." });
  }
  return items;
}

const COLOUR = { good: "var(--aito-teal)", bad: "var(--cta)", note: "var(--text-muted)" } as const;

/** The top left: who the segment is, and what can be done about it. */
export default function SegmentProfile({ summary, selected }: { summary: ProfilesSummary; selected: string }) {
  const found = findSegment(summary, selected);
  if (!found) return <div className="card card-sub">Select a segment.</div>;
  const { segment, trait } = found;
  const items = actionableItems(summary, selected);
  return (
    <div className="card" style={{ borderTop: "3px solid var(--aito-teal)" }}>
      <div className="card-sub">{TRAIT_TITLE[trait]}</div>
      <div className="page-title" style={{ fontSize: 24, margin: "2px 0 6px" }}>{segment.value}</div>
      <div style={{ fontSize: 14, lineHeight: 1.55 }}>{definitionOf(summary, selected)}</div>
      <div className="card-sub" style={{ marginTop: 6 }}>
        {segment.customers.toLocaleString("fi-FI")} customers, {Math.round(segment.share * 100)} % of those profiled.
      </div>
      <div style={{ fontWeight: 600, margin: "14px 0 6px" }}>What to do</div>
      {items.map((item, i) => (
        <div key={i} style={{ display: "flex", gap: 8, fontSize: 13, lineHeight: 1.5, margin: "4px 0" }}>
          <span style={{ width: 8, height: 8, borderRadius: "50%", background: COLOUR[item.tone], marginTop: 6, flex: "none" }} />
          <span>{item.text}</span>
        </div>
      ))}
      <div className="card-sub" style={{ marginTop: 10 }}>
        Observed in simulated data; a difference does not prove the action caused it.{" "}
        <Link href="/shopkeeper/?run=winback">The Shopkeeper agent runs the win-back →</Link>
      </div>
    </div>
  );
}
