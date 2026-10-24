/**
 * Patterns' lead sentences: each section opens with what its strongest
 * rows mean for the shop, and what to do about it (ADR 0041). Every
 * number comes from a row the section shows, with its interval; the
 * sentence names no row that didn't clear the section's bar.
 */

import { fieldLabel, valueLabel } from "@/components/shop-analytics/LiftParts";
import type { ShopAnalyticsPair, ShopLiftRow, ShopLiftSection, ShopSearchWordSection } from "@/lib/types";

const fmt = (n: number) => n.toLocaleString("en-US");
export const liftWithInterval = (r: { lift: number; interval_low: number; interval_high: number }) =>
  `${r.lift.toFixed(2)}× [${r.interval_low.toFixed(2)}–${r.interval_high.toFixed(2)}]`;

/** Products described by a state the owner controls ("on offer", "at a 15–20 % discount"). */
function leverPhrase(row: ShopLiftRow): string | null {
  if (row.field === "product_state.on_offer" && row.value === "true") return "on offer";
  if (row.field === "product_state.discount_band" && row.value !== "none") {
    // Bands read "10-15", "15-20", "20+".
    const band = row.value.endsWith("+") ? `${row.value.slice(0, -1)} % or more` : `${row.value.replace("-", "–")} %`;
    return `at a discount of ${band}`;
  }
  if (row.field === "product_state.age" && row.value === "new") return "that are new";
  return null;
}

export function funnelLead(section: ShopLiftSection, kpiNoun: string): string | null {
  const lever = section.rows.find((r) => r.lift > 1 && leverPhrase(r) !== null);
  const stars = section.rows.find((r) => r.field === "product_sku.rating_band" && r.value !== "unrated" && r.lift < 1);
  if (lever) {
    const held = stars ? `, and products with ${valueLabel(stars)} ${liftWithInterval(stars)}` : "";
    return `Products ${leverPhrase(lever)} get ${liftWithInterval(lever)} their share of ${kpiNoun}${held}. ` +
      `For what a discount would do to one product's sales, open it in Product › What if.`;
  }
  const top = section.rows[0];
  return top ? `${fieldLabel(top.field)} = ${valueLabel(top)}: ${liftWithInterval(top)} its share of ${kpiNoun}.` : null;
}

export function whoLead(section: ShopLiftSection): string | null {
  const top = section.rows.find((r) => r.lift > 1);
  const option = section.options.find((o) => o.id === section.selected);
  if (!top || !option) return null;
  const what = `${valueLabel(top)} ${top.field === "product_sku.dietary" ? "food" : "products"}`;
  const action = option.group === "Season"
    ? `stock up on them before ${option.label.toLowerCase()}`
    : "feature them for these households";
  return `${option.label}: ${what} sell ${liftWithInterval(top)} their share of all order lines. Act on it: ${action}.`;
}

export function basketLead(pairs: ShopAnalyticsPair[]): string | null {
  const top = pairs.find((p) => p.lift > 1);
  if (!top) return null;
  const without = top.orders_with_first - top.orders_with_both;
  return `${top.first} baskets hold ${top.second.toLowerCase()} ${liftWithInterval(top)} as often as the average basket: ` +
    `put them together in the cart and the drawer. ${fmt(without)} of ${fmt(top.orders_with_first)} ` +
    `${top.first.toLowerCase()} orders had none.`;
}

export function searchWordLead(section: ShopSearchWordSection): string | null {
  const top = section.rows.find((w) => w.lift > 1);
  const lost = [...section.never_bought].sort((a, b) => b.impressions - a.impressions)[0];
  const parts = [];
  if (top) parts.push(`Searches for “${top.word}” end in a purchase ${liftWithInterval(top)} as often as the average search.`);
  if (lost) {
    parts.push(`“${lost.word}” had ${fmt(lost.impressions)} impressions and no purchase (about ${lost.expected_purchases} ` +
      `expected): check what that search returns.`);
  }
  return parts.length ? parts.join(" ") : null;
}
