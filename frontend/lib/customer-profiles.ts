/** The Customers view's data (ADR 0053). */

export interface Segment {
  key?: string; value: string; customers: number; share: number; churn_rate?: number; avg_spend_eur?: number; thin?: boolean;
  revenue_eur?: number; revenue_share?: number;
  profit_eur?: number; profit_12m_eur?: number; profit_per_customer_eur?: number; profit_per_customer_ci?: [number, number] | null;
  margin?: number; profit_share?: number;
}

export interface ResponseCell {
  rows: number; order_rate: number | null; thin: boolean; lift_points: number | null; margin_points: number | null; clear: boolean | null;
  profit_eur: number | null; profit_lift_eur: number | null; profit_margin_eur: number | null; profit_clear: boolean | null;
}

export interface ResponseEntry {
  none: { rows: number; order_rate: number | null; profit_eur: number | null }; actions: Record<string, ResponseCell>;
}

export interface FunnelCounts { impressions: number; clicks: number; carts: number; purchases: number }

export interface RankedQuintile { customers: number; lift: number; mean_share: number; segment_share: Record<string, number> }

export interface PreferenceRanking {
  label: string; customers: number; mean_share: number; curve: number[]; quintiles: RankedQuintile[];
  top_over_average: number; top_over_bottom: number | null;
}

export interface ProfilesSummary {
  release: string; simulated: boolean; stale: boolean; scope: "release" | "release-not-sandbox"; customers: number; profiled: number; not_profiled: number;
  profiled_revenue_eur: number; profiled_profit_eur: number; gross_margin: number;
  profit_distribution: { customers: number; median_eur: number; top_tenth_share: number; losing_money: number };
  overall: Segment; definitions: Record<string, string>;
  funnel: Record<string, FunnelCounts>; preference_ranking: Record<string, PreferenceRanking>;
  relations: Relation[]; preferences: Record<string, PreferenceGroup>;
  by_trait: Record<"offer" | "price" | "rating" | "pets" | "diets", Segment[]>;
  response: Record<string, ResponseEntry>;
}

export interface CustomerProfile {
  customer_id: string; name?: string; profiled: boolean; lines?: number; offer: string; price: string; rating: string;
  profit_eur?: number; offer_share?: number; cheaper_share?: number; rating_gap?: number | null; pets?: string[]; diets?: string[];
}

export const TRAIT_TITLE: Record<string, string> = {
  all: "Everyone", offer: "Buys on offer", price: "Prices they pick", rating: "Ratings they pick", pets: "Pets they buy for",
  diets: "Diets their pet's food is made for",
};

/** The trait groups in the order the list shows them. */
export const TRAITS = ["offer", "price", "rating", "pets", "diets"] as const;

export const ACTION_TITLE: Record<string, string> = {
  email: "Email", ad: "Ad", discount: "Discount", voucher: "Voucher", apology: "Apology",
};

export interface TraitRef { trait: string; value: string }

export interface Relation {
  if: TraitRef; then: TraitRef; customers_with: number; share_with: number; share_without: number;
  points: number; margin_points: number; clear: boolean;
}

export interface PreferenceRow {
  item: string; name?: string; buyers: number; share: number; share_others: number; points: number; margin_points: number; clear: boolean;
}

export interface PreferenceGroup {
  pet: string; customers: number; others: number;
  categories: PreferenceRow[]; brands: PreferenceRow[]; products: PreferenceRow[];
}

/** A segment by its key ("all", or "trait:value"); the list, the picker and the panes look segments up the same way. */
export function findSegment(summary: ProfilesSummary, key: string): { segment: Segment; trait: string } | null {
  if (key === "all") return { segment: summary.overall, trait: "all" };
  for (const trait of TRAITS) {
    const segment = summary.by_trait[trait].find((s) => (s.key ?? `${trait}:${s.value}`) === key);
    if (segment) return { segment, trait };
  }
  return null;
}

/** The segment's key, whichever trait group it came from. */
export function keyOf(trait: string, s: Segment): string {
  return s.key ?? `${trait}:${s.value}`;
}

export function definitionOf(summary: ProfilesSummary, key: string): string {
  const trait = key.split(":")[0];
  return summary.definitions[key] ?? summary.definitions[`_${trait}`] ?? "";
}
